"""How much easier a big target is to hit, as his sheet says it.

A Large or Huge body is bought as a Physical Complication whose text states
the cost in the book's own terms: the Bestiary's Riding Horse carries "Large
(4m; +2 OCV for others to hit, +2 to PER Rolls for others to perceive)". The
number is read off that text, so a sheet that says +4 is +4. Peter's ruling,
2026-11-27: read it off the sheet.
"""
from __future__ import annotations

import re
from typing import Any

_EASIER_TO_HIT = re.compile(r"\+\s*(\d+)\s*OCV\s+for\s+others\s+to\s+hit", re.I)


def ocv_to_hit(target: Any) -> int:
    """The OCV every attacker gets against ``target`` for his size."""
    from kirby_combat.complications import complications_of

    best = 0
    for comp in complications_of(target):
        if comp.xmlid != "PHYSICALLIMITATION":
            continue
        found = _EASIER_TO_HIT.search(comp.name or "")
        if found:
            best = max(best, int(found.group(1)))
    return best
