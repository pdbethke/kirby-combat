"""Sense-based perception for combat (spec 2026-06-13-combat-perception-design).

Pure engine logic: who perceives whom, across the Targeting Senses, accounting
for line-of-sight, per-Sense-Group Invisibility, Stealth, and Mind Scan.
"""
from __future__ import annotations

from dataclasses import dataclass

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
                # Penetrative is a sense modifier (an adder/option on the power).
                blob = " ".join([
                    (getattr(p, "alias", "") or ""),
                    " ".join((getattr(a, "option_alias", "") or "")
                             for a in getattr(p, "adders", []) or []),
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
