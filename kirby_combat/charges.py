"""Ammunition --- how many uses a Charged power has, and how many are gone.

`HeroCombatState.used_charges` has existed a long time: declared,
documented as "Power xmlid -> number of charges spent in this combat",
and serialized in BOTH directions. Nothing ever wrote it and nothing ever
read it, so nobody in any fight this engine has run has ever had to
reload. PeterB found it with one question: "are you recording ammo?"

The counts were in the builds the whole time. HSEG's Colt Peacemaker is
`<MODIFIER XMLID="CHARGES" OPTIONID="SIX">`, the Winchester '73 has
sixteen, and Doc Holliday's coach gun has ONE --- which he has been firing
four times a fight.

6E1 p.334: "Each slot of a Charges power lets the character use the power
the defined number of times per day." Charges are uses.

COUNTED BY THE POWER'S OWN ID, never its xmlid. Doc carries a Shotgun and
a Colt Peacemaker and BOTH are RKA, so counting by type would empty one
gun by firing the other. That is the same "identity is an id" rule
`_power_action_id` already refuses to bend --- matching on xmlid + name is
what once made 630 corpus objects share a token.
"""
from __future__ import annotations

import re
from typing import Any

#: HD writes the count as a WORD in OPTIONID ("SIX") and as a numeral in
#: the rendered alias. The numeral is read first because it needs no table
#: and covers counts this map has never heard of; the words are the
#: fallback for a build whose alias did not survive.
_WORDS = {
    "ZERO": 0, "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5,
    "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10, "TWELVE": 12,
    "SIXTEEN": 16, "TWENTY": 20, "THIRTYTWO": 32, "SIXTYFOUR": 64,
    "ONEHUNDRED": 100, "TWOHUNDRED": 200, "TWOFIFTY": 250,
}


def charges_on(power: Any) -> int | None:
    """How many uses this power has, or None when it is not limited.

    NONE IS NOT ZERO. "Unlimited" and "empty" must never be the same
    answer --- confusing them would silently switch off every innate power
    in the corpus.
    """
    for mod in (getattr(power, "assigned_modifiers", None) or []):
        if (getattr(mod, "xmlid", "") or "").upper() != "CHARGES":
            continue
        numeral = re.search(r"\d+", str(getattr(mod, "alias_for_vector", "") or ""))
        if numeral:
            return int(numeral.group(0))
        word = (getattr(mod, "option_id", "") or "").upper().replace(" ", "")
        if word in _WORDS:
            return _WORDS[word]
        return None
    return None


def spent_charges(session: Any, combatant_id: str) -> dict[str, int]:
    """`power id -> how many times this combatant has fired it`.

    Folded from the log rather than tracked, like everything else in this
    engine that a caller would otherwise have to keep in step by hand.
    Attribution needs both halves the resolvers emit: `ActionDeclared`
    carries who, `ActionResolved` carries what.
    """
    out: dict[str, int] = {}
    mine: set[str] = set()
    for event in list(getattr(session, "event_log", None) or []):
        kind = getattr(event, "kind", "")
        if kind == "ActionDeclared":
            if getattr(event, "combatant_id", "") == combatant_id:
                mine.add(getattr(event, "id", ""))
        elif kind == "ActionResolved":
            if getattr(event, "declaration_event_id", "") not in mine:
                continue
            payload = getattr(event, "result_payload", None) or {}
            source = payload.get("power_source_id")
            if source:
                out[str(source)] = out.get(str(source), 0) + 1
    return out
