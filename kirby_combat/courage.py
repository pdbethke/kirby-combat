"""What a man's complications say about his nerve, read once for every rule.

Lifted out of `tactics/catalog/abort_or_stand.py` (2026-11-27) so the Abort
doctrine and the nerve check (`nerve`) read one list: a man the Abort advice
calls a coward is the man who runs when his side breaks, and a fearless one
neither ducks nor quits. Words are matched in the text a player wrote
(`complications_of(...).name`).
"""
from __future__ import annotations

from typing import Any

COWARDLY = ("not brave", "coward", "cowardly", "craven", "fearful")
FEARLESS = ("vengeful", "no fear", "fearless", "reckless", "death wish",
            "overconfiden")


def complication_saying(complications, words) -> Any | None:
    """The first complication whose text carries any of ``words``."""
    for comp in complications or []:
        text = (getattr(comp, "name", "") or "").lower()
        if any(w in text for w in words):
            return comp
    return None
