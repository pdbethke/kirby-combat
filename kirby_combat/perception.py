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
