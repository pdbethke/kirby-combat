"""Reading the fight: the Tactics (else INT) roll at the top of his Phase.

6E1 p.93, Tactics (paraphrased): a character with it knows how to fight
effectively in small-unit combat; a made roll gives him hints about what his
opponent intends and how to counter it, and a failed one means he can't
think of a way to beat the enemy, or settles on the wrong tactic.

WHY THE ENGINE ROLLS IT. Seats read this roll --- a plan's soft trigger
("did he notice the fight changed?"), whether a long shot is worth a Set,
and in time which lessons from past fights a fighter can draw on --- and
until 0.33 the seat rolled it itself, on the session's dice and outside
the log. A roll is a rule and the log must hold it (PeterB, 2026-11-10:
rule-based decisions are not the AI package's). So the loop rolls it once a
Phase for the man whose Phase it is, records `FightRead`, and every seat
reads that one answer (`PhaseSituation.fight_read`).

RULING (ported from the deleted api driver's `_notices_soft_trigger`):
"Tactics roll first; if the character has no Tactics, fall back to a plain
INT roll. Tactics is a BONUS to reading a fight, not a gate."
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


def _rolled_this_phase(session: "CombatSession", actor_id: str) -> list:
    from kirby_combat.pre_attacks.in_the_phase import _in_this_phase

    return [e for e in _in_this_phase(session, actor_id)
            if getattr(e, "kind", None) == "FightRead" and e.combatant_id == actor_id]


def reading_roll(actor: Any) -> tuple[str, int]:
    """(skill, target number): his Tactics if he has it, else his INT Roll."""
    skill_roll = getattr(actor, "skill_roll_value", None)
    tactics = skill_roll("TACTICS") if callable(skill_roll) else None
    if tactics is not None:
        return "TACTICS", int(tactics)
    from kirby_combat.perception import per_roll_target

    return "INT", int(per_roll_target(actor))


def read_the_fight(session: "CombatSession", actor_id: str, roller) -> "CombatSession":
    """Roll his read of the fight, once a Phase. Unchanged when he is down
    or has already rolled this Phase."""
    from kirby_combat.enumeration import is_down
    from kirby_combat.mental.mind_control import roll_succeeds
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import FightRead, make_author_engine

    actor = session.combatants[actor_id]
    if is_down(actor) or _rolled_this_phase(session, actor_id):
        return session
    if roller is None:
        raise ValueError("the read-the-fight roll needs the Phase's dice")
    skill, target = reading_roll(actor)
    rolled = sum(roller.roll_dice(3))
    return apply_event(session, FightRead(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id=actor_id, skill=skill, roll=rolled, target_number=target,
        made=roll_succeeds(rolled, target), made_by=target - rolled,
        turn=int(session.timeline.turn), segment=int(session.timeline.segment),
    ))


def fight_read(session: "CombatSession", actor_id: str):
    """This Phase's `FightRead` for him, or None if none was rolled."""
    rolled = _rolled_this_phase(session, actor_id)
    return rolled[-1] if rolled else None
