"""Reading a character's complications -- the pure half.

Three of the original four helpers never touched a database: they inspect
`Complication` objects a caller has already loaded. Those move here.

The fourth, `complications_for`, reads rows and stays in the consumer. That
is the same split Darkness settled: the RULE about a complication belongs to
the engine, the ROWS belong to whoever owns the database.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Complication

def _extract_keywords(text: str) -> tuple[str, ...]:
    if not text:
        return ()
    text_lower = text.lower()
    found: list[str] = []
    for pattern, tag in _KEYWORD_PATTERNS:
        if re.search(pattern, text_lower):
            if tag not in found:
                found.append(tag)
    return tuple(found)

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
