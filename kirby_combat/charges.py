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

A FRAMEWORK'S CHARGES ARE ONE SUPPLY. 6E1 p.409: "the Multipower as a
whole has as many Charges as are bought for the reserve; each slot does not
have that many Charges --- all the slots, taken together, have that many
Charges" (and p.403: such slots "do not cost END"). So uses are counted by
POOL (`charge_pool`): a power's own id when it carries the Charges, its
framework's when the reserve does. The slots of a charged Multipower had no
Charges at all here and fired without limit (42 slots in the local library).

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


def charge_pool(power: Any) -> tuple[str, int] | None:
    """``(pool id, how many uses it holds)`` for a build power, or None when
    nothing limits it: its own Charges, else its framework reserve's (6E1
    p.403, p.409). NONE IS NOT ZERO, as for `charges_on`."""
    own = charges_on(power)
    if own is not None:
        return str(getattr(power, "id", "")), own
    parent = getattr(power, "parent", None)
    if parent is not None:
        shared = charges_on(parent)
        if shared is not None:
            return str(getattr(parent, "id", "")), shared
    return None


def has_charges_left(source: Any, spent: dict[str, int] | None) -> bool:
    """Is there a use left in this build power, given ``spent`` (the
    `spent_charges` count)? A power nothing limits never runs dry, and a
    power with no build behind it (``source`` None) is not limited."""
    if source is None:
        return True
    pool = charge_pool(source)
    if pool is None:
        return True                      # innate: never runs dry
    key, capacity = pool                 # a framework's slots share one
    return (spent or {}).get(key, 0) < capacity


def _pools_of(combatant: Any) -> dict[str, str]:
    """`power id -> pool id` for every build power that draws on a pool
    other than its own: the slots of a charged framework."""
    from kirby_combat.identity import build_in_play

    out: dict[str, str] = {}
    build = build_in_play(combatant) if combatant is not None else None
    for power in [*(getattr(build, "powers", None) or []),
                  *(getattr(build, "equipment", None) or [])]:
        pool = charge_pool(power)
        if pool is not None and pool[0] != str(getattr(power, "id", "")):
            out[str(getattr(power, "id", ""))] = pool[0]
    return out


def spent_charges(session: Any, combatant_id: str) -> dict[str, int]:
    """`pool id -> how many Charges this combatant has used from it`: a
    power's own id, or its framework's when the reserve carries the
    Charges (`charge_pool`).

    Folded from the log rather than tracked, like everything else in this
    engine that a caller would otherwise have to keep in step by hand.
    Attribution needs both halves the resolvers emit: `ActionDeclared`
    carries who, `ActionResolved` carries what.
    """
    out: dict[str, int] = {}
    mine: set[str] = set()
    pools = _pools_of((getattr(session, "combatants", None) or {}).get(combatant_id))
    for event in list(getattr(session, "event_log", None) or []):
        kind = getattr(event, "kind", "")
        if kind == "ChargeSpent":
            # Keeping a Charged Constant power up (`upkeep`, 6E1 p.403).
            if getattr(event, "combatant_id", "") == combatant_id:
                source = str(getattr(event, "power_source_id", "") or "")
                key = pools.get(source, source)
                out[key] = out.get(key, 0) + 1
            continue
        if kind == "ClipChanged":
            # A FRESH CLIP (6E1 p.371, `reload`): uses restart from here.
            if getattr(event, "combatant_id", "") == combatant_id:
                out[str(getattr(event, "pool_id", ""))] = 0
            continue
        if kind == "ActionDeclared":
            if getattr(event, "combatant_id", "") == combatant_id:
                mine.add(getattr(event, "id", ""))
        elif kind == "ActionResolved":
            if getattr(event, "declaration_event_id", "") not in mine:
                continue
            payload = getattr(event, "result_payload", None) or {}
            source = payload.get("power_source_id")
            if source:
                # 6E1 p.329: an Autofire burst "must ... use up Charges ...
                # for each shot", and its use row says how many it fired
                # (`actions/autofire_attack.py`). Every other use is one.
                shots = payload.get("shots_fired")
                used = 1 if shots is None else int(shots)
                key = pools.get(str(source), str(source))
                out[key] = out.get(key, 0) + used
    return out


# ---------------------------------------------------------------------------
# Clips (6E1 p.371)
# ---------------------------------------------------------------------------

def _charges_modifier(power: Any):
    for mod in (getattr(power, "assigned_modifiers", None) or []):
        if (getattr(mod, "xmlid", "") or "").upper() == "CHARGES":
            return mod
    return None


def _adder(mod: Any, xmlid: str):
    for adder in (getattr(mod, "assigned_adders", None) or []):
        if (getattr(adder, "xmlid", "") or "").upper() == xmlid:
            return adder
    return None


def clips_on(power: Any) -> int:
    """How many clips its Charges come in. 6E1 p.371: "Charges are normally
    purchased in a single 'clip'"; HD's ``CLIPS`` adder at level L is
    "x[LVL] Clips" with LVLPOWER 2, i.e. 2^L clips. The Charges option is
    the count in ONE clip. A power with no Charges has no clips (0)."""
    mod = _charges_modifier(power)
    if mod is None:
        return 0
    clips = _adder(mod, "CLIPS")
    if clips is None:
        return 1
    return 2 ** int(getattr(clips, "levels", 0) or 0)


def increased_reload(power: Any) -> str | None:
    """HD's ``INCREASEDRELOAD`` option (6E1 p.371's Increased Reloading Time
    table: EXTRAPHASE = 2 Full Phases, TURN, MINUTE ...), or None for the
    ordinary Full Phase."""
    mod = _charges_modifier(power)
    adder = _adder(mod, "INCREASEDRELOAD") if mod is not None else None
    if adder is None:
        return None
    opt = getattr(getattr(adder, "_selected_option", None), "xmlid", None) \
        or getattr(adder, "option_id", None)
    return str(opt or "").upper() or None


def clips_changed(session: Any, combatant_id: str, pool_id: str) -> int:
    """How many fresh clips he has put in that pool this fight."""
    return sum(1 for e in (getattr(session, "event_log", None) or [])
               if getattr(e, "kind", "") == "ClipChanged"
               and getattr(e, "combatant_id", "") == combatant_id
               and str(getattr(e, "pool_id", "")) == pool_id)
