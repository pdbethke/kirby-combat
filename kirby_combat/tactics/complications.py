"""Reading a character's complications -- the pure half.

Three of the original four helpers never touched a database: they inspect
`Complication` objects a caller has already loaded. Those move here.

The fourth, `complications_for`, reads rows and stays in the consumer. That
is the same split Darkness settled: the RULE about a complication belongs to
the engine, the ROWS belong to whoever owns the database.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Complication

# `_extract_keywords` USED TO LIVE HERE AND COULD NEVER RUN. It was carved
# out of the parked kirby-api with its body intact and neither of its
# dependencies -- `re` was not imported and `_KEYWORD_PATTERNS` was not
# defined -- so every call raised `NameError: name '_KEYWORD_PATTERNS' is
# not defined`. Nothing called it, which is why nothing noticed.
#
# Deleted rather than repaired. Keyword extraction already has one live
# home, `complications.py::_keywords`, which is what fills
# `Complication.trigger_keywords`; reviving this would have been a second
# vocabulary for the same job, mapping patterns to semantic tags where the
# live one keeps the words. Both tactics that read complications
# (`bait_enraged`, `exploit_susceptibility`) search by xmlid anyway.

def has_complication(complications: list[Complication], xmlid: str) -> bool:
    """Predicate: target_xmlid match (case-insensitive)."""
    target = xmlid.upper()
    return any(c.xmlid == target for c in complications)

def find_complication(
    complications: list[Complication], *, xmlid: str | None = None,
    keyword: str | None = None,
) -> Complication | None:
    """Find first matching complication by xmlid OR by trigger
    keyword. Returns None if no match."""
    for c in complications:
        if xmlid and c.xmlid == xmlid.upper():
            return c
        if keyword and keyword.lower() in c.trigger_keywords:
            return c
    return None
