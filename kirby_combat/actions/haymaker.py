"""Haymaker — a named attack that lands a Segment late, +4 DC (6E2 p.70, p.73).

6E2 p.70, paraphrased: a Haymaker takes an extra Segment. The character
begins it on one of his Phases (a Half Phase Action, so he may Half Move
first), but the blow isn't launched until the very end of the NEXT Segment,
after everyone who acts in that Segment has acted. It may be any attack; the
Combat Maneuvers table (p.73) gives it +4 DC and -5 DCV. He may Abort to a
defensive Action in the Segment it goes off, but that ruins the Haymaker.
And the risk is the point: the target may move, or he may be hit while he
stands winding up.

HOW THE ENGINE KEEPS IT. One ``ActionDeclared(action_type="haymaker")``
names the attack offer he wound up (``attack_action_id``), the target, and
the (turn, segment) it lands at. It is pending until an ``ActionResolved``
closes it: landed, or ruined. While pending he is at -5 DCV
(`recording.py`). At the end of the landing Segment the loop
(`loop/run.py`) asks for that same attack off his menu as it stands THEN,
and resolves it with +4 DC added to its dice (kirby-cost's
``add_damage_classes``). If the attack is no longer on his menu --- the
target moved out of reach or out of sight, or he can't act --- the Haymaker
is ruined: that is the risk p.70 describes, and the engine doesn't
re-target it for him.

WHAT IT CAN BE. A Normal or Killing Damage attack or Strike without an
Advantage that changes its Damage Classes' price (6E2 p.99-100). p.70 also
allows a Haymaker of a Drain or a Mental Blast with the GM setting what it
adds; those aren't offered, because "the GM determines" is not a number.

REPLACES: ``Haymaker.modifiers_for_pending_attack``, which returned
{dc_bonus: 4, dcv_delta: -5} and had no caller outside its own tests, so a
Haymaker cost a Phase and did nothing; and ``declare``'s
``planned_attack_action_type``, which named a kind rather than an attack.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared,
    ActionResolved,
    make_author_combatant,
    make_author_engine,
)

#: 6E2 p.73, Combat Maneuvers table.
DC_BONUS = 4
DCV_DELTA = -5

#: A Haymaker's id prefix: ``haymaker:<the attack offer's own id>``.
PREFIX = "haymaker:"


def _next_segment(turn: int, segment: int) -> tuple[int, int]:
    return (turn, segment + 1) if segment < 12 else (turn + 1, 1)


def can_haymaker(power) -> bool:
    """Whether +4 DC is a number for this attack (see the module docstring)."""
    return (power is not None
            and getattr(power, "damage_type", None) in ("normal", "killing")
            and not (power.armor_piercing or power.penetrating
                     or power.increased_stun_mult or getattr(power, "avad", False)))


def with_bonus(power):
    """The attack's power with Haymaker's +4 DC on its dice (6E2 p.101)."""
    from dataclasses import replace

    from kirby_cost.engine.damage import Dice, add_damage_classes

    if not can_haymaker(power):
        raise ValueError(f"{getattr(power, 'name', power)!r}: no DC number to add a Haymaker to")
    dice = add_damage_classes(
        Dice(full=int(power.damage_dice), half=bool(power.half_die),
             plus_one=bool(power.plus_one), minus_one=bool(getattr(power, "minus_one", False))),
        power.damage_type, DC_BONUS)
    return replace(power, damage_dice=dice.full, half_die=dice.half,
                   plus_one=dice.plus_one, minus_one=dice.minus_one)


def declare(session: CombatSession, combatant_id: str, *,
            attack_action_id: str, target_id: str) -> tuple[CombatSession, ActionDeclared]:
    """He begins a Haymaker of that attack; it lands at the end of the next Segment."""
    from kirby_combat.session.apply import apply_event

    lands_turn, lands_segment = _next_segment(session.timeline.turn, session.timeline.segment)
    evt = ActionDeclared(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(UTC),
        author=make_author_combatant(combatant_id),
        combatant_id=combatant_id,
        action_type="haymaker",
        targets=[target_id],
        parameters={"attack_action_id": attack_action_id,
                    "lands_turn": lands_turn, "lands_segment": lands_segment},
    )
    return apply_event(session, evt), evt


def pending(session: CombatSession, combatant_id: str) -> ActionDeclared | None:
    """His Haymaker in the air, if he has one: declared, neither landed nor ruined."""
    closed = {e.declaration_event_id for e in session.event_log
              if isinstance(e, ActionResolved)}
    for evt in reversed(session.event_log):
        if (isinstance(evt, ActionDeclared) and evt.combatant_id == combatant_id
                and evt.action_type == "haymaker"):
            return None if evt.id in closed else evt
    return None


def dcv_delta(session: CombatSession, combatant_id: str) -> int:
    """-5 DCV while he winds up (6E2 p.73)."""
    return DCV_DELTA if pending(session, combatant_id) is not None else 0


def due(session: CombatSession) -> list[ActionDeclared]:
    """The Haymakers that land at the end of the Segment the clock is in."""
    now = (session.timeline.turn, session.timeline.segment)
    out = []
    for cid in session.combatants:
        evt = pending(session, cid)
        if evt is not None and (evt.parameters["lands_turn"],
                                evt.parameters["lands_segment"]) == now:
            out.append(evt)
    return out


def close(session: CombatSession, declaration: ActionDeclared, *,
          landed: bool, reason: str) -> CombatSession:
    """Write down how it ended: landed, or ruined and why."""
    from kirby_combat.session.apply import apply_event

    evt = ActionResolved(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(UTC),
        author=make_author_engine(),
        declaration_event_id=declaration.id,
        result_payload={"kind": "haymaker", "landed": landed, "ruined": not landed,
                        "reason": reason, "combatant_id": declaration.combatant_id,
                        "attack_action_id": declaration.parameters["attack_action_id"]},
    )
    return apply_event(session, evt)


def land_due(session: CombatSession, *, template, roller) -> CombatSession:
    """At the very end of a Segment, after everyone in it has acted: every
    Haymaker due now goes off, or is ruined (6E2 p.70)."""
    from dataclasses import replace

    from kirby_combat.enumeration import is_down
    from kirby_combat.loop.registry import resolve_chosen
    from kirby_combat.loop.run import _situation_for
    from kirby_combat.statuses import stunned_or_recovering_for

    for declaration in due(session):
        cid = declaration.combatant_id
        actor = session.combatants.get(cid)
        if actor is None or is_down(actor) or stunned_or_recovering_for(session, cid):
            session = close(session, declaration, landed=False,
                            reason="he could not act when it was due")
            continue
        wanted = declaration.parameters["attack_action_id"]
        offer = next((o for o in _situation_for(session, cid).menu
                      if o.action_id == wanted), None)
        if offer is None:
            session = close(session, declaration, landed=False,
                            reason="the attack was no longer there to make")
            continue
        boosted = replace(offer, _attack_view=with_bonus(offer._attack_view))
        resolved = resolve_chosen(session, actor, boosted, template=template, roller=roller)
        session = close(resolved.session, declaration, landed=True,
                        reason=f"+{DC_BONUS} DC")
    return session
