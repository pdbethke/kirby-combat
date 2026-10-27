"""Rolling With A Punch (6E2 p.90): half the damage, more Knockback.

"Roll With A Punch allows a character to take less damage from a HTH attack.
This Maneuver is unique because a character may perform it after he's been
struck by an opponent's attack (i.e., after the opponent's Attack Roll
succeeds, but before he rolls damage). To Roll With A Punch, the character
must make an Attack Roll against his attacker's OCV (like Block); this roll
has a -2 OCV penalty. If successful, the character takes only half the STUN
and BODY that the attack would have normally done. (Halve the total after
defenses have been applied.) However, the attacker rolls one less die for
Knockback ... A character may not Roll With A Punch against multiple
attacks". And: "A character may Abort to Roll With A Punch. However, he
cannot do so if he's unable to act or Abort to an Action."

WHEN HE DECIDES. The loop asks a defender one question, before anything is
rolled (`loop/reactions.react_to_attack`, 6E2 p.24's moment). The book lets
him decide on Rolling With A Punch after the blow has landed. RULING: the
answer he gives then is CONDITIONAL --- "if it lands, I roll with it" --- and
nothing is spent unless it does. The "ready" row records the choice; the
attack door (`actions/recording.resolve_attack_in_session`) asks
`try_roll_with_punch` once it knows the blow hit, and only then is the Abort
declared (his next Phase given up, or the Held Action used) and the roll
made. Since he would know nothing at the door he did not know at the
question except that it hit, the decision is the one the book gives him.

"Any sort of HTH Combat attack" (p.90) and never "multiple attacks": offered
only against a single hand-to-hand blow (`OFFERED_AGAINST`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.models import AttackInput
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate

#: The Abort's ``to_action`` and the reaction's kind.
ROLL_WITH_PUNCH = "roll_with_punch"
#: The conditional choice, recorded when he makes it.
READY = "roll_with_punch_ready"

#: 6E2 p.90: "this roll has a -2 OCV penalty".
OCV_PENALTY = -2

#: The single hand-to-hand blows he may roll with. Not Sweep, Multiple
#: Attack or Rapid Fire: "may not Roll With A Punch against multiple
#: attacks" (p.90).
OFFERED_AGAINST = frozenset({"attack", "strike", "maneuver", "move_strike",
                             "reposition_strike"})


def _now():
    return datetime.now(timezone.utc)


def declare_ready(session: "CombatSession", defender_id: str,
                  attacker_id: str) -> "CombatSession":
    """Record his conditional choice. Spends nothing (see the module)."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ActionResolved, make_author_combatant

    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=_now(),
        author=make_author_combatant(defender_id), declaration_event_id="",
        result_payload={
            "kind": READY, "defender_id": defender_id,
            "attacker_id": attacker_id,
            "turn": session.timeline.turn, "segment": session.timeline.segment,
        },
    ))


def standing_ready(session: "CombatSession", defender_id: str,
                   attacker_id: str):
    """The unspent ready row for this blow, or None.

    It stands for the NEXT blow this attacker lands on him in this Segment
    and no other: walking back from the end, a row of his attack on this
    man, or a roll already made against the ready row, ends it.
    """
    timeline = session.timeline
    for event in reversed(session.event_log):
        if getattr(event, "kind", "") != "ActionResolved":
            continue
        payload = getattr(event, "result_payload", None) or {}
        kind = payload.get("kind")
        if kind == ROLL_WITH_PUNCH and payload.get("defender_id") == defender_id:
            return None
        if (payload.get("target_id") == defender_id
                and getattr(event.author, "id", None) == attacker_id
                and kind != READY):
            return None
        if (kind == READY and payload.get("defender_id") == defender_id
                and payload.get("attacker_id") == attacker_id):
            if (payload.get("turn"), payload.get("segment")) != (
                    timeline.turn, timeline.segment):
                return None
            return event
    return None


def _target_number(defender_ocv: int, attacker_ocv: int) -> int:
    """6E2 p.36's 11 + OCV - DCV, the attacker's OCV standing in for DCV as
    a Block's does (6E2 p.59)."""
    return 11 + int(defender_ocv) - int(attacker_ocv)


def try_roll_with_punch(
    session: "CombatSession", attack: "AttackInput", template: "CombatTemplate",
    *, roller,
) -> tuple["CombatSession", dict[str, Any] | None]:
    """At the attack door, once the blow has HIT: does he roll with it?

    Returns the session (the Abort declared and the roll recorded) and the
    roll's payload, or the session untouched and None when he chose nothing.
    The caller halves the damage taken and takes a die off the Knockback
    roll on a success.
    """
    from kirby_combat.actions.held_action import HeldAction
    from kirby_combat.actions.reactive.abort import (
        mark_aborting, mark_aborting_with_held,
    )
    from kirby_combat.cv_modifiers import effective_ocv_for
    from kirby_combat.loop.reactions import may_abort, usable_hold
    from kirby_combat.resolution.to_hit import resolve_to_hit
    from kirby_combat.sense_penalties import HTH

    defender_id = getattr(attack.target, "id", None)
    attacker_id = getattr(attack.attacker, "id", None)
    if defender_id not in session.combatants or attacker_id not in session.combatants:
        return session, None
    ready = standing_ready(session, defender_id, attacker_id)
    if ready is None:
        return session, None
    if not may_abort(session, defender_id, session.combatants[attacker_id]):
        # "he cannot do so if he's unable to act or Abort to an Action"
        # (p.90): something between the question and the blow took that
        # away. The choice lapses, recorded.
        return _record(session, ready, defender_id, attacker_id,
                       {"rolled": False, "success": False,
                        "reason": "cannot abort"}), None

    held = usable_hold(session, defender_id)
    if held is not None:
        session, _ = HeldAction.release(
            session, held.id,
            trigger_observed=f"Aborted to {ROLL_WITH_PUNCH} against {attacker_id}")
        session, _ = mark_aborting_with_held(session, defender_id,
                                             to_action=ROLL_WITH_PUNCH)
    else:
        session, _ = mark_aborting(session, defender_id, to_action=ROLL_WITH_PUNCH)

    attacker_ocv = int(resolve_to_hit(attack, template).effective_ocv)
    defender_ocv = int(effective_ocv_for(session, defender_id, against=attacker_id,
                                         combat_type=HTH)) + OCV_PENALTY
    needed = _target_number(defender_ocv, attacker_ocv)
    rolled = sum(roller.roll_dice(3))
    # 6E2 p.37: a 3 always hits and an 18 always misses.
    success = rolled == 3 or (rolled != 18 and rolled <= needed)
    payload = {"rolled": True, "roll": rolled, "target_number": needed,
               "defender_ocv": defender_ocv, "attacker_ocv": attacker_ocv,
               "success": success}
    session = _record(session, ready, defender_id, attacker_id, payload)
    return session, payload


def _record(session, ready, defender_id: str, attacker_id: str, extra: dict):
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ActionResolved, make_author_combatant

    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=_now(),
        author=make_author_combatant(defender_id),
        declaration_event_id=ready.id,
        result_payload={"kind": ROLL_WITH_PUNCH, "defender_id": defender_id,
                        "attacker_id": attacker_id, **extra},
    ))
