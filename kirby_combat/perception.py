"""Sense-based perception for combat (spec 2026-06-13-combat-perception-design).

Pure engine logic: who perceives whom, across the Targeting Senses, accounting
for line-of-sight, per-Sense-Group Invisibility, Stealth, and Mind Scan.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from kirby_combat.dice import RandomRoller
from kirby_combat.resolution.line_of_sight import has_line_of_sight
from kirby_combat.scene.geometry import (
    first_blocking_surface, first_blocking_wall, path_crosses_polygon,
    point_in_polygon_xy,
)

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
    """PER roll target for an observer, from kirby-cost.

    Was `9 + INT // 5`. Truncation is not the rule: an INT of 13 rolls 12-,
    and this reported 11- for it.
    """
    from kirby_cost.engine.rolls import characteristic_roll, roll_constants
    base, denominator = roll_constants(observer.hero)
    return characteristic_roll(observer.hero.characteristic_value("INT"),
                               base=base, denominator=denominator)


def range_modifier(distance_m: float) -> int:
    """The HERO Range Modifier (6E2 p40), a penalty (≤0) that applies to all
    PER rolls at distance (6E2 p13). No modifier out to 8m; −2 after 8m, then
    −2 for each doubling of range thereafter: −2 at 9-16m, −4 at 17-32m,
    −6 at 33-64m, and so on."""
    d = float(distance_m)
    if d <= 8.0:
        return 0
    return -2 * math.ceil(math.log2(d / 8.0))


def _roll_3d6_succeeds(target: int, roller) -> bool:
    """Auditable 3d6 ≤ target via the session roller (like the throw spec)."""
    return sum(roller.roll_dice(3)) <= int(target)


def disbelieve_image(*, per_target: int, image_penalty: int, roller) -> bool:
    """A single observer's PER-Roll-to-disbelieve an Image (6E1 p238-240).

    An observer with a line to the Image may roll PER to see through it, at a
    penalty equal to the Image's complexity. Returns True if *this* observer
    perceives the illusion as fake: 3d6 ≤ (per_target − image_penalty).
    ``per_target`` is the observer's PER roll target (``per_roll_target``);
    ``image_penalty`` is the Image's concealment/complexity PER penalty (≥0).
    """
    return _roll_3d6_succeeds(int(per_target) - int(image_penalty), roller)


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


def _invisibility_has_no_fringe(hero) -> bool:
    """True if the target's INVISIBILITY power carries the No Fringe adder
    (XMLID ``NOFRINGE`` on ``assigned_adders``; falls back to ``adders`` /
    free-text for synthetic stubs). No Fringe removes the tell-tale shimmer,
    so the ≤2m Fringe PER roll can't perceive it (6E1 p340)."""
    for p in getattr(hero, "powers", None) or []:
        if (getattr(p, "xmlid", None) or "").upper() != "INVISIBILITY":
            continue
        adders = (getattr(p, "assigned_adders", None)
                  or getattr(p, "adders", None) or [])
        for a in adders:
            ax = (getattr(a, "XMLID", None) or getattr(a, "xmlid", None) or "")
            if ax.upper() == "NOFRINGE":
                return True
            alias = (getattr(a, "alias", "") or "").lower()
            if "no fringe" in alias:
                return True
    return False


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


def flash_groups(power) -> frozenset[str]:
    """The Sense Group(s) a single FLASH power covers (sense-affecting §1).

    A FLASH power encodes its Sense Group(s) identically to INVISIBILITY: the
    primary group in ``option_id`` (a ``*GROUP`` token) plus extra groups as
    ``assigned_adders`` GROUP tokens. Defaults to the Sight Group (the HERO
    default) for a present-but-unparsed FLASH power; returns an empty set for a
    non-FLASH power so callers can probe any power uniformly.

    Reuses the same field-reading as ``_power_invisibility_groups`` — a FLASH
    power carries the group on the exact same shape."""
    if (getattr(power, "xmlid", None) or "").upper() != "FLASH":
        return frozenset()
    found = _power_invisibility_groups(power)
    return frozenset(found or {SIGHT})   # never empty for a present FLASH power


def darkness_groups(power) -> frozenset[str]:
    """The Sense Group(s) a single DARKNESS power occludes (sense-affecting §2).

    A DARKNESS power encodes its Sense Group(s) on the exact same shape as
    INVISIBILITY/FLASH: the primary group in ``option_id`` (a ``*GROUP`` token)
    plus extra groups as ``assigned_adders`` GROUP tokens. Defaults to the Sight
    Group (the HERO default) for a present-but-unparsed DARKNESS power; returns
    an empty set for a non-DARKNESS power so callers can probe any power
    uniformly."""
    if (getattr(power, "xmlid", None) or "").upper() != "DARKNESS":
        return frozenset()
    found = _power_invisibility_groups(power)
    return frozenset(found or {SIGHT})   # never empty for a present DARKNESS power


def darkness_personal_immunity(power) -> bool:
    """True if a DARKNESS power carries the Personal Immunity adder (XMLID
    ``PERSONALIMMUNITY`` on ``assigned_adders``; falls back to ``adders`` /
    free-text for synthetic stubs). Personal Immunity lets the creating
    combatant perceive through their own Darkness (6E1 p140)."""
    adders = (getattr(power, "assigned_adders", None)
              or getattr(power, "adders", None) or [])
    for a in adders:
        ax = (getattr(a, "XMLID", None) or getattr(a, "xmlid", None) or "")
        if ax.upper() == "PERSONALIMMUNITY":
            return True
        alias = (getattr(a, "alias", "") or "").lower()
        if "personal immunity" in alias:
            return True
    return False


@dataclass(frozen=True)
class Perception:
    """Result of ``perceive(observer, target)``. ``via`` lists the senses that
    perceive; the per-type flags drive the driver's targeting gate."""
    targetable_physical: bool      # a non-mental Targeting Sense reaches the target
    targetable_mental: bool        # mental LOS holds (any Targeting Sense / Mind Scan)
    via: tuple[str, ...] = ()      # e.g. ("normal_sight",) / ("mindscan",)
    kind: str = "visible"          # visible|occluded|invisible|hidden|out_of_range
    # Non-targeting-sense perception is a documented v1 deferral: senses()
    # returns only Targeting senses, so perceive() never emits a
    # "perceived_nontargeting" kind in v1.
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


def _distance(o, t, scene) -> float:
    """Euclidean distance (metres) between two combatants in the scene.
    Returns 0.0 when either position is unknown (scene-less call)."""
    positions = getattr(scene, "combatant_positions", None) or {} if scene else {}
    a = positions.get(o.id)
    b = positions.get(t.id)
    if a is None or b is None:
        return 0.0
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5


def _opposed_perceives(per_target: int, stealth_target: int, roller) -> tuple[bool, int, int]:
    """Opposed 3d6 perception contest (spec §1d). The observer makes a PER
    roll (3d6 ≤ ``per_target``) and the hider makes a Stealth roll
    (3d6 ≤ ``stealth_target``). The observer perceives iff its *margin of
    success* is at least the hider's — i.e.::

        (per_target - per_roll) >= (stealth_target - stealth_roll)

    Ties go to the observer. (A failed PER roll has a negative margin, so a
    hider who makes their Stealth roll wins; a blown Stealth roll loses.)
    Returns (perceived, per_roll, stealth_roll)."""
    per_roll = sum(roller.roll_dice(3))
    stealth_roll = sum(roller.roll_dice(3))
    perceived = (per_target - per_roll) >= (stealth_target - stealth_roll)
    return perceived, per_roll, stealth_roll


def _sight_los(observer, target, scene, sense) -> tuple[bool, str | None]:
    """Does a sight-like sense have a clear LoS to the target?
    Penetrative senses ignore occluders. A scene-less call / missing positions
    is treated as no occlusion gate (clear). Returns ``(clear, occluder_id)``,
    where ``occluder_id`` is the REAL id of the nearest blocking wall (so the
    Plan 2 GUI can surface the actual occluder) or ``None`` when clear."""
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
    if clear:
        return True, None
    # Recover the actual occluder's id (not the sentinel "occluded") so the
    # GUI can name it. A wall wins when both apply -- it is the nearer, more
    # specific answer; a floor is the fallback ("the rooftop blocks it").
    wall = first_blocking_wall(o, t, getattr(scene, "walls", None) or [])
    if wall is not None:
        return False, getattr(wall, "id", None)
    surface = first_blocking_surface(o, t, getattr(scene, "surfaces", None))
    return False, (getattr(surface, "id", None) if surface is not None else None)


def _point_in_zone(p, zone) -> bool:
    """True if a Position ``p`` lies inside a darkness_zone's polygon footprint
    (xy) within its elevation range. Mirrors ``constructs_containing``."""
    poly = getattr(zone, "polygon_xy", None)
    if not poly:
        return False
    lo, hi = getattr(zone, "elevation_range_m", (0.0, 0.0))
    if not (lo <= p.z <= hi):
        return False
    return point_in_polygon_xy((p.x, p.y), poly)


def _darkness_blocks(observer, target, scene, sense) -> bool:
    """True if a darkness_zone Construct occludes ``sense``'s Sense Group on the
    observer→target ray (sense-affecting §2). The gate is group-keyed: only a
    zone whose ``sense_group`` matches ``sense.group`` blocks. The ray is
    occluded when it crosses the zone polygon OR either endpoint lies inside it
    (within the zone's elevation range). The creating combatant with Personal
    Immunity (``creator_immune``) is exempt for their own zone.

    Fail-open: a scene-less call, missing positions, or no darkness zones → no
    occlusion (returns False)."""
    if scene is None:
        return False
    constructs = getattr(scene, "constructs", None) or []
    if not constructs:
        return False
    positions = getattr(scene, "combatant_positions", None) or {}
    o = positions.get(observer.id)
    t = positions.get(target.id)
    if o is None or t is None:
        return False                 # missing positions → no darkness gate
    for c in constructs:
        if getattr(c, "kind", None) != "darkness_zone":
            continue
        if getattr(c, "sense_group", None) != sense.group:
            continue
        if (observer.id == getattr(c, "source_combatant_id", None)
                and getattr(c, "creator_immune", False)):
            continue                 # creator with Personal Immunity sees through
        poly = getattr(c, "polygon_xy", None)
        if not poly:
            continue
        if (path_crosses_polygon((o.x, o.y), (t.x, t.y), poly)
                or _point_in_zone(o, c) or _point_in_zone(t, c)):
            return True
    return False


_FRINGE_RANGE_M = 2.0


def perceive(observer, target, scene, *, target_invisible: bool = False,
             target_hidden: bool = False, stealth_movement_modifier: int = 0,
             observer_flashed_groups: frozenset[str] = frozenset(),
             roller=None) -> Perception:
    """Per-sense perception (spec §1). Sight + bought Targeting senses resolve
    LoS/occlusion; per-Sense-Group Invisibility blocks the covered senses
    (with a ≤2m Fringe PER roll unless the power has No Fringe); a Hidden
    target runs an opposed Stealth-vs-PER contest against any clear Sight-group
    sense. Mental senses give non-LOS mental targeting (Task 6 adds the lock).
    Pure: no DB, no mutation."""
    if roller is None:
        roller = RandomRoller()

    via_physical: list[str] = []
    via_mental: list[str] = []
    occluder: str | None = None
    detail: dict = {}

    # ``target_invisible`` is the caller's authority that the target is
    # currently Invisible (set by the driver, or a GM toggle). Use the build's covered
    # Sense Group(s) when its INVISIBILITY power names them; otherwise default
    # to the Sight Group (the HERO default) so the flag still has effect even
    # when the static build carries no INVISIBILITY power.
    inv_groups = frozenset()
    inv_no_fringe = False
    if target_invisible:
        inv_groups = invisibility_groups(target.hero) or frozenset({SIGHT})
        inv_no_fringe = _invisibility_has_no_fringe(target.hero)

    for sense in observer.senses():
        if not getattr(sense, "functional", True):
            continue
        # Flash: a sense whose group the OBSERVER currently has flashed can't
        # perceive at all (sense-affecting §1). Group-generic, so a MENTAL-group
        # flash skips a mental sense (Mind Scan) too — checked before the mental
        # branch below so a flashed mental sense gives no mental LOS.
        if sense.group in observer_flashed_groups:
            continue
        # Darkness: a darkness_zone occluding this sense's group on the
        # observer→target ray blocks the sense entirely (sense-affecting §2).
        # Run BEFORE the mental branch AND before _sight_los's penetrative
        # short-circuit, so a Sight-Darkness blocks a penetrative Sight sense
        # (Nightvision) and a Mental-Darkness blocks Mind Scan. The creating
        # combatant with Personal Immunity is exempt for their own zone.
        if _darkness_blocks(observer, target, scene, sense):
            continue
        # Mental sense (Mind Scan / Mental Awareness): handle FIRST, before the
        # generic per-group Invisibility skip below. A mental sense perceives
        # the mind regardless of line-of-sight, walls, or a *physical*
        # Invisibility (Mind Scan is non-LOS — 6E2 p16) — it is defeated ONLY
        # when the target's Invisibility covers the MENTAL group. So gate it on
        # MENTAL ∈ inv_groups, never on the generic ``sense.group in
        # inv_groups`` (which would let a Sight-group Invisibility wrongly blind
        # a Mind Scan). No Fringe applies to physical senses only, so a mental
        # sense gives no fringe perception.
        if sense.mental:
            if MENTAL not in inv_groups:
                via_mental.append(_via_token(sense.xmlid))
            continue
        # Invisibility: a non-mental sense whose group the target's Invisibility
        # covers can't normally perceive it — but a ≤2m physical sense can spot
        # the Fringe (the tell-tale shimmer) on a PER roll, unless the power has
        # No Fringe (6E1 p340).
        if sense.group in inv_groups:
            if (not inv_no_fringe
                    and "fringe" not in detail
                    and _distance(observer, target, scene) <= _FRINGE_RANGE_M):
                per_target = per_roll_target(observer)
                per_roll = sum(roller.roll_dice(3))
                if per_roll <= per_target:
                    detail["fringe"] = {"per": per_target, "per_roll": per_roll}
                    via_physical.append("fringe")
            continue
        clear, occ = _sight_los(observer, target, scene, sense)
        if not clear:
            occluder = occluder or occ
            continue
        # Hidden target: only Sight-group senses are fooled by Stealth (IR /
        # Radar / Mind Scan aren't). Run the opposed contest once.
        if target_hidden and sense.group == SIGHT and "stealth" not in detail:
            stealth_target = target.skill_roll_value("STEALTH")
            if stealth_target is None:
                # No Stealth skill → the target can't actually hide → perceived.
                via_physical.append(_via_token(sense.xmlid))
                continue
            # PER takes the Range Modifier at distance (6E2 p13/p40); the
            # hider's Stealth takes the movement modifier the driver supplies
            # for how the hider moved this phase (Western Hero p29: Noncombat
            # −5 … creep ≤2m +2). A PER reduced to ≤0 by range can't perceive.
            rng = range_modifier(_distance(observer, target, scene))
            eff_per = per_roll_target(observer) + rng
            eff_stealth = stealth_target + int(stealth_movement_modifier)
            detail["stealth"] = eff_stealth
            detail["per"] = eff_per
            detail["range_modifier"] = rng
            if eff_per <= 0:
                # Too far to perceive distinctly even on a 3 (6E2 p9) → hidden.
                continue
            perceived, per_roll, stealth_roll = _opposed_perceives(
                eff_per, eff_stealth, roller)
            detail["per_roll"] = per_roll
            detail["stealth_roll"] = stealth_roll
            if perceived:
                via_physical.append(_via_token(sense.xmlid))
            continue
        via_physical.append(_via_token(sense.xmlid))

    if via_physical:
        kind = "visible"
    elif occluder:
        kind = "occluded"
    elif target_hidden:
        kind = "hidden"
    else:
        kind = "invisible"
    return Perception(
        targetable_physical=bool(via_physical),
        # Sight also gives mental LOS (you can target a mind you can see).
        targetable_mental=bool(via_mental) or bool(via_physical),
        via=tuple(via_physical + via_mental),
        kind=kind,
        occluder_id=occluder,
        detail=detail,
    )


def _has_talent(hero, xmlid: str) -> bool:
    """True if the hero has the named Talent. Danger Sense / Combat Sense load
    via the HDCLoader as ``hero.talents`` entries (verified against
    ``Black Paladin.hdc``: ``<TALENT XMLID="DANGER_SENSE">`` → an entry on
    ``hero.talents`` with ``.xmlid == "DANGER_SENSE"`` and nothing in
    ``hero.powers``). We scan BOTH ``talents`` and ``powers`` so the check is
    robust to alternate load shapes / synthetic stubs."""
    want = (xmlid or "").upper()
    for coll in (getattr(hero, "talents", None), getattr(hero, "powers", None)):
        for t in coll or []:
            if (getattr(t, "xmlid", None) or "").upper() == want:
                return True
    return False


def has_combat_sense(hero) -> bool:
    """True if the character has the Combat Sense Talent (spec §1a).

    This is the SEAM Plan 2 needs to negate the HtH-blind penalty: a combatant
    with Combat Sense can fight effectively without sight. The HtH negation
    itself lives in Plan 2; here we only surface the capability. Reuses the
    ``_has_talent`` scan over ``talents`` + ``powers`` for ``COMBAT_SENSE``."""
    return _has_talent(hero, "COMBAT_SENSE")


def is_surprised(*, observer, attacker, scene, roller=None,
                 attacker_invisible: bool = False,
                 attacker_hidden: bool = False) -> bool:
    """Whether ``observer`` is Surprised by ``attacker`` (spec §1e).

    The engine signal: the observer is Surprised iff it perceives the attacker
    by NO sense (no physical, no mental) AND lacks Danger Sense. Danger Sense
    always negates Surprise (6E1 — it warns of imminent danger regardless of
    LoS). (Non-targeting-sense perception isn't modeled in v1 — see Perception
    — so there's no third perception channel to check here.)

    ``attacker_invisible`` / ``attacker_hidden`` carry the attacker's
    concealment (the whole point of a sneak attack) into the perception check —
    an Invisible or Hidden attacker the observer can't otherwise perceive
    should come up Surprised.

    The "observer is not already expecting attacks" gate (turn/awareness state)
    is applied by the driver, which knows the combat clock — this function only
    answers the pure perception question."""
    if _has_talent(observer.hero, "DANGER_SENSE"):
        return False
    p = perceive(observer, attacker, scene,
                 target_invisible=attacker_invisible,
                 target_hidden=attacker_hidden,
                 roller=roller)
    return not (p.targetable_physical or p.targetable_mental)
