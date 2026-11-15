"""Powers a man switches on for himself and keeps up: Desolidification and
Invisibility.

Both are Constant personal powers (6E1 p.192 Desolidification, p.243
Invisibility): nothing is aimed, nothing is left on the board. He turns one
on, it stays on while he pays for it, and he turns it off. This module is
the switch and the fold; what each one CHANGES lives with its rule
(`desolidification` for what crosses between solid and desolid,
`concealment.is_invisible` for who can be seen).

THE RULES (6E1 unless marked):

  * "Other Zero Phase Actions include activating a Power, turning off a
    Power ... Some Zero Phase Actions (such as turning on a specific Power)
    can only be performed once in a Phase" (6E2 p.20). Both offers are Zero
    Phase, and turning a given power ON is once a Phase.
  * A Constant power costs END to activate, which is that Phase's END, and
    every Phase after it is kept up (p.129-130). Kept up by `kept_up`, with
    every other kept-up power: END each Phase, its Multipower slot holding
    the reserve (p.402), down when he is Stunned or Knocked Out as a
    Segment ends (p.347, 6E2 p.107) or Recovers (6E2 p.131).
  * A Persistent power "is assumed to be on at all times" (p.130): never
    switched, on whenever its slot holds the reserve. RULING: it is on for
    this module's purposes and is not offered or kept up here.

Before this, Invisibility counted as on for anyone who owned it
(`concealment.is_invisible` read the build), so a man whose Invisibility
sat in an empty Multipower slot was unseen the whole fight; and
Desolidification was never offered at all.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class _Terms:
    xmlid: str
    on_kind: str      # the offer that turns it on
    off_kind: str     # the offer that turns it off (`kept_up.DROP_KIND`)
    on_type: str      # ``result_payload["type"]`` of the row that says so
    off_type: str
    noun: str


class Switched(Enum):
    DESOLID = _Terms("DESOLIDIFICATION", "desolidify", "drop_desolid",
                     "desolidified", "desolid_ended", "Desolidification")
    INVISIBLE = _Terms("INVISIBILITY", "turn_invisible", "drop_invisible",
                       "invisible", "invisible_ended", "Invisibility")

    @property
    def terms(self) -> _Terms:
        return self.value


def power_of(hero: Any, switch: Switched) -> Any | None:
    """The first power of ``switch``'s kind on ``hero``, or None."""
    for p in (getattr(hero, "powers", None) or []):
        if (getattr(p, "xmlid", "") or "").upper() == switch.terms.xmlid:
            return p
    return None


def _power_in_play(session, combatant_id: str, switch: Switched) -> Any | None:
    from kirby_combat.identity import build_in_play

    owner = session.combatants.get(combatant_id)
    return None if owner is None else power_of(build_in_play(owner), switch)


def is_persistent(power: Any) -> bool:
    from kirby_combat.enumeration import _has_modifier

    return power is not None and _has_modifier(power, "PERSISTENT")


def switched_on(session, combatant_id: str, switch: Switched) -> bool:
    """Folded from the log: his last ``on_type`` row not yet followed by an
    ``off_type`` one."""
    on = False
    t = switch.terms
    for evt in session.event_log:
        payload = getattr(evt, "result_payload", None)
        if not isinstance(payload, dict) or payload.get("combatant_id") != combatant_id:
            continue
        if payload.get("type") == t.on_type:
            on = True
        elif payload.get("type") == t.off_type:
            on = False
    return on


def is_on(session, combatant_id: str, switch: Switched) -> bool:
    """On now: switched on, or Persistent with its slot holding the reserve."""
    if switched_on(session, combatant_id, switch):
        return True
    power = _power_in_play(session, combatant_id, switch)
    if not is_persistent(power):
        return False
    from kirby_combat.upkeep import slot_still_allocated

    return slot_still_allocated(session, combatant_id, power)


def switched_on_ids(session, switch: Switched) -> list[str]:
    """Everyone who switched ``switch`` on and has it up (Persistent ones are
    never kept up, so they are not here)."""
    return [cid for cid in session.combatants if switched_on(session, cid, switch)]


def turned_on_this_phase(session, combatant_id: str, switch: Switched) -> bool:
    """6E2 p.20: turning a given power on is once a Phase."""
    from kirby_combat.pre_attacks.in_the_phase import _in_this_phase

    return any(
        getattr(evt, "kind", None) == "ActionDeclared"
        and getattr(evt, "combatant_id", None) == combatant_id
        and getattr(evt, "action_type", None) == switch.terms.on_kind
        for evt in _in_this_phase(session, combatant_id)
    )


def can_turn_on(session, actor, switch: Switched, *, template) -> bool:
    from kirby_combat.endurance import end_available
    from kirby_combat.upkeep import end_of, not_built, slot_still_allocated

    power = _power_in_play(session, actor.id, switch)
    if power is None or is_persistent(power) or is_on(session, actor.id, switch):
        return False
    if turned_on_this_phase(session, actor.id, switch) or not_built(power):
        return False
    if not slot_still_allocated(session, actor.id, power):
        return False
    held = actor.at_split(power)
    left = end_available(session, actor.id, power=held, template=template)
    return left is None or left >= end_of(held)


_SAYS = {
    Switched.DESOLID: (
        "physical and energy attacks pass through you, but you cannot hit, "
        "Grab, Flash or mentally attack anyone solid. Mental powers, Flash "
        "and Presence Attacks still reach you"),
    Switched.INVISIBLE: (
        "enemies who cannot perceive you with another Sense cannot target "
        "you, and an attack they do not see coming catches them Surprised"),
}


def turn_on_offers(session, actor, *, template) -> list:
    """An offer to turn each one on that he can turn on now."""
    from kirby_combat.enumeration import LegalAction

    out = []
    for switch in Switched:
        if not can_turn_on(session, actor, switch, template=template):
            continue
        power = _power_in_play(session, actor.id, switch)
        name = getattr(power, "name", None) or switch.terms.noun
        out.append(LegalAction(
            action_id=f"{switch.terms.on_kind}:{getattr(power, 'id', '')}",
            kind=switch.terms.on_kind, target_id=None,
            power_xmlid=switch.terms.xmlid, power_name=name,
            summary=(f"Turn on {name} ({switch.terms.noun}; a Zero Phase "
                     f"Action, 6E2 p.20): {_SAYS[switch]}. Costs END every "
                     f"Phase you keep it up"),
        ))
    return out


def _row(session, combatant_id: str, payload: dict, *, by_engine: bool):
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import (
        ActionResolved, make_author_combatant, make_author_engine,
    )

    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_engine() if by_engine else make_author_combatant(combatant_id),
        declaration_event_id="",
        result_payload={**payload, "combatant_id": combatant_id},
    ))


def turn_on(session, actor, switch: Switched, *, template):
    """He turns it on: a declaration, its END (p.130), and the row."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ActionDeclared, make_author_combatant
    from kirby_combat.upkeep import pay_for_the_phase

    if not can_turn_on(session, actor, switch, template=template):
        raise ValueError(f"{actor.id!r} cannot turn on {switch.terms.noun} now")
    power = _power_in_play(session, actor.id, switch)
    session = apply_event(session, ActionDeclared(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(actor.id), combatant_id=actor.id,
        action_type=switch.terms.on_kind, targets=[actor.id],
        parameters={"power_xmlid": switch.terms.xmlid},
    ))
    session, unpaid = pay_for_the_phase(session, actor.id, actor.at_split(power),
                                        template=template)
    if unpaid is not None:
        raise ValueError(f"{actor.id!r} could not pay for {switch.terms.noun}: "
                         f"{unpaid.value}")
    return _row(session, actor.id, {
        "type": switch.terms.on_type, "kind": switch.terms.on_kind,
        "power_name": getattr(power, "name", None),
        "power_source_id": str(getattr(power, "id", "") or ""),
        "segment": session.timeline.segment,
    }, by_engine=False)


def turn_off(session, combatant_id: str, switch: Switched, reason) -> Any:
    """It is off; ``reason`` is the `upkeep.UpkeepEnd` that ended it."""
    return _row(session, combatant_id,
                {"type": switch.terms.off_type, "reason": reason.value},
                by_engine=True)
