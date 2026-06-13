"""Sense-based perception for combat (spec 2026-06-13-combat-perception-design).

Pure engine logic: who perceives whom, across the Targeting Senses, accounting
for line-of-sight, per-Sense-Group Invisibility, Stealth, and Mind Scan.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.resolution.line_of_sight import has_line_of_sight

# Sense-group names — MUST match actions/flash.py's sense_group strings
# ("sight" / "hearing" / "mental" / "radio"; smell as "smell").
SIGHT = "sight"
HEARING = "hearing"
MENTAL = "mental"
RADIO = "radio"
SMELL = "smell"

# The Targeting Senses (HD6 p26) and the Sense Group each is bought into by
# default. Sight Group is the only default Targeting group; the listed senses
# are Targeting when present. xmlid -> group.
_TARGETING_SENSE_XMLIDS: dict[str, str] = {
    "NORMALSIGHT": SIGHT,
    "INFRAREDPERCEPTION": SIGHT,     # almost always bought into the Sight Group (6E2 p11)
    "NIGHTVISION": SIGHT,
    "ULTRAVIOLETPERCEPTION": SIGHT,
    "ACTIVESONAR": HEARING,          # Targeting when bought; its own group
    "RADAR": RADIO,
    "SPATIALAWARENESS": SIGHT,       # a sight-like targeting sense
    "MINDSCAN": MENTAL,
}

_MENTAL_SENSE_XMLIDS = {"MINDSCAN", "MENTAL_AWARENESS"}


@dataclass(frozen=True)
class SenseCapability:
    """One Targeting Sense the observer has. `group` is the Sense Group it
    belongs to (Invisibility/Flash/Darkness affect by group). `penetrative`
    sees through occluders; `mental` is a Mind-Scan-style non-LOS sense."""
    xmlid: str
    name: str
    group: str
    is_targeting: bool = True
    penetrative: bool = False       # 6E1 p215 — sees through walls
    mental: bool = False            # Mind Scan family — non-LOS (6E2 p16)
    functional: bool = True         # v1 always True; Flash/Darkness flip it later


def _sense_capabilities(hero) -> list["SenseCapability"]:
    out: list[SenseCapability] = [
        SenseCapability(xmlid="NORMALSIGHT", name="Normal Sight", group=SIGHT)
    ]
    seen = {"NORMALSIGHT"}

    def _walk(power_list):
        for p in power_list or []:
            x = (getattr(p, "xmlid", None) or "").upper()
            if x in _TARGETING_SENSE_XMLIDS and x not in seen:
                seen.add(x)
                # Penetrative is a sense modifier (an adder/option on the
                # power). Loaders surface adders as ``assigned_adders`` (each
                # with ``.XMLID``); fall back to ``adders`` for synthetic stubs.
                adders = (getattr(p, "assigned_adders", None)
                          or getattr(p, "adders", None) or [])
                blob = " ".join([
                    (getattr(p, "alias", "") or ""),
                    " ".join(
                        (getattr(a, "XMLID", None) or getattr(a, "xmlid", "") or "")
                        + " " + (getattr(a, "option_alias", "") or "")
                        + " " + (getattr(a, "alias", "") or "")
                        for a in adders),
                ]).lower()
                out.append(SenseCapability(
                    xmlid=x,
                    name=str(getattr(p, "alias", None) or x),
                    group=_TARGETING_SENSE_XMLIDS[x],
                    is_targeting=True,
                    penetrative=("penetrative" in blob),
                    mental=(x in _MENTAL_SENSE_XMLIDS),
                ))
            _walk(getattr(p, "sub_powers", None))

    _walk(getattr(hero, "powers", None))
    return out


def per_roll_target(observer) -> int:
    """PER roll target = 9 + INT/5 (6E1). ``observer`` is a HeroCombatant."""
    return 9 + int(observer.hero.characteristic_value("INT")) // 5


def _roll_3d6_succeeds(target: int, roller) -> bool:
    """Auditable 3d6 ≤ target via the session roller (like the throw spec)."""
    return sum(roller.roll_dice(3)) <= int(target)


# Invisibility's covered Sense Group(s) come from two real-shape places on a
# loaded INVISIBILITY power (verified against the HSB bestiary corpus, e.g.
# UNDEAD_GHOST_HSB.hdc — Sight+Hearing+Smell):
#   1. the power's primary OPTION  -> ``power.option_id`` == "SIGHTGROUP"
#      (NOTE: ``option_alias`` is None on the loaded object; the group token
#       lives in ``option_id`` / the raw XML ``OPTIONID``).
#   2. extra groups as adders     -> each ``assigned_adders`` entry whose
#      ``XMLID`` is a *GROUP token, e.g. "HEARINGGROUP", "SMELLGROUP".
# We map both the GROUP-token xmlids and free-text aliases to a sense group, so
# the parse is robust whether we get a token, an alias, or a plain stub.
_GROUP_TOKENS: dict[str, str] = {
    "SIGHTGROUP": SIGHT,
    "HEARINGGROUP": HEARING,
    "MENTALGROUP": MENTAL,
    "RADIOGROUP": RADIO,
    "SMELLGROUP": SMELL,
}

# Free-text alias/option fragments → sense group (fallback / synthetic stubs).
_GROUP_KEYWORDS: list[tuple[str, str]] = [
    ("sight", SIGHT), ("hearing", HEARING), ("sound", HEARING),
    ("mental", MENTAL), ("radio", RADIO), ("smell", SMELL), ("taste", SMELL),
]


def _groups_from_text(blob: str) -> set[str]:
    return {g for kw, g in _GROUP_KEYWORDS if kw in blob}


def _power_invisibility_groups(p) -> set[str]:
    """Sense Group(s) one INVISIBILITY power covers, from its real load shape."""
    found: set[str] = set()

    # 1. Primary group: the power's OPTION token (option_id / option / optionid).
    for attr in ("option_id", "optionid", "option"):
        tok = (getattr(p, attr, None) or "")
        if tok and tok.upper() in _GROUP_TOKENS:
            found.add(_GROUP_TOKENS[tok.upper()])

    # 2. Extra groups: GROUP-token adders. Loaders surface these as
    #    ``assigned_adders`` (XMLID upper) or, on stubs, ``adders``.
    adders = (getattr(p, "assigned_adders", None)
              or getattr(p, "adders", None) or [])
    for a in adders:
        ax = (getattr(a, "XMLID", None) or getattr(a, "xmlid", None) or "")
        if ax.upper() in _GROUP_TOKENS:
            found.add(_GROUP_TOKENS[ax.upper()])

    # 3. Free-text fallback (option_alias / aliases) — robust to odd encodings.
    blob = " ".join([
        (getattr(p, "option_alias", "") or ""),
        (getattr(p, "alias", "") or ""),
        " ".join((getattr(a, "option_alias", "") or "") + " "
                 + (getattr(a, "alias", "") or "") for a in adders),
    ]).lower()
    # Only let the alias fallback ADD groups it clearly names beyond the bare
    # power name "invisibility" (which contains no group word).
    found |= _groups_from_text(blob)

    return found


def invisibility_groups(hero) -> frozenset[str]:
    """The Sense Group(s) this character's Invisibility covers. Default: the
    Sight Group (the HERO default when the power doesn't specify otherwise).

    Returns an empty set when the character has no Invisibility power; never
    returns empty for a *present* Invisibility power (defaults to {SIGHT})."""
    groups: set[str] = set()
    for p in getattr(hero, "powers", None) or []:
        if (getattr(p, "xmlid", None) or "").upper() != "INVISIBILITY":
            continue
        found = _power_invisibility_groups(p)
        groups |= (found or {SIGHT})   # never empty for a present power
    return frozenset(groups)


@dataclass(frozen=True)
class Perception:
    """Result of ``perceive(observer, target)``. ``via`` lists the senses that
    perceive; the per-type flags drive the kirby-api targeting gate."""
    targetable_physical: bool      # a non-mental Targeting Sense reaches the target
    targetable_mental: bool        # mental LOS holds (any Targeting Sense / Mind Scan)
    via: tuple[str, ...] = ()      # e.g. ("normal_sight",) / ("mindscan",)
    kind: str = "visible"          # visible|occluded|invisible|hidden|out_of_range|perceived_nontargeting
    occluder_id: str | None = None
    detail: dict = field(default_factory=dict)


# Canonical ``via`` token per sense xmlid. Most are the lowercased xmlid
# (e.g. MINDSCAN -> "mindscan"); a few read better snake-cased.
_VIA_ALIASES: dict[str, str] = {
    "NORMALSIGHT": "normal_sight",
}


def _via_token(xmlid: str) -> str:
    x = (xmlid or "").upper()
    return _VIA_ALIASES.get(x, x.lower())


def _sight_los(observer, target, scene, sense) -> tuple[bool, str | None]:
    """Does a sight-like sense have a clear LoS to the target?
    Penetrative senses ignore occluders. A scene-less call / missing positions
    is treated as no occlusion gate (clear). Returns (clear, occluder_id)."""
    if sense.penetrative:
        return True, None
    if scene is None:
        return True, None
    positions = getattr(scene, "combatant_positions", None) or {}
    o = positions.get(observer.id)
    t = positions.get(target.id)
    if o is None or t is None:
        return True, None            # scene-less / no positions → no occlusion gate
    clear = has_line_of_sight(scene, o, t)
    return clear, (None if clear else "occluded")


def perceive(observer, target, scene, *, target_invisible: bool = False,
             target_hidden: bool = False, roller=None) -> Perception:
    """Per-sense perception (spec §1). This task covers the Sight + bought
    Targeting-sense LoS/occlusion core. Invisibility per-group is wired
    structurally (a sense whose group the target's Invisibility covers can't
    perceive); Fringe/Stealth/Mind-Scan-lock depth lands in Tasks 5-6.
    Pure: no DB, no mutation."""
    via_physical: list[str] = []
    via_mental: list[str] = []
    occluder: str | None = None

    inv_groups = invisibility_groups(target.hero) if target_invisible else frozenset()

    for sense in observer.senses():
        if not getattr(sense, "functional", True):
            continue
        # Invisibility: a sense whose group the target's Invisibility covers
        # can't perceive it (Fringe/Stealth resolution comes in Task 5).
        if sense.group in inv_groups:
            continue
        if sense.mental:
            # Mind Scan / mental sense — non-LOS (Task 6 adds the lock gate).
            via_mental.append(_via_token(sense.xmlid))
            continue
        clear, occ = _sight_los(observer, target, scene, sense)
        if clear:
            via_physical.append(_via_token(sense.xmlid))
        elif occ:
            occluder = occluder or occ

    if via_physical:
        kind = "visible"
    elif occluder:
        kind = "occluded"
    else:
        kind = "invisible"
    return Perception(
        targetable_physical=bool(via_physical),
        # Sight also gives mental LOS (you can target a mind you can see).
        targetable_mental=bool(via_mental) or bool(via_physical),
        via=tuple(via_physical + via_mental),
        kind=kind,
        occluder_id=occluder,
    )
