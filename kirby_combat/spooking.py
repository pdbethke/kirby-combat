"""A horse spooks at gunfire, and a horse that spooks bolts.

THE RULE. Western Hero p.113: a horse not trained for it "will need to make
a Presence Roll ... or become frightened and panic". RULING (Peter,
2026-11-27): the roll is made each time it is shot at or a shot lands near
it, with its Timid complication against it (`courage.COWARDLY`, -5 when
Strong, the penalty `nerve` already gives); failing, it bolts. "Near" is
within NEAR_M of where the shot was aimed: a judgement, for Peter to confirm.

A bolt is the nerve rule's ``fled`` (`NerveRolled`), so the loop breaks it
off the field exactly as it does a man who ran, and its cover goes with it
(`bodies`). A bolted horse does not roll again.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

#: How close a shot must land to spook a horse (judgement).
NEAR_M = 2.0


def _horses(session) -> list[Any]:
    from kirby_combat.enumeration import is_down
    from kirby_combat.nerve import nerve_state
    from kirby_combat.side import Side

    return [c for c in session.combatants.values()
            if Side.of(c).neutral and not is_down(c) and nerve_state(session, c.id) is None]


def after_a_shot(session: "CombatSession", attack: Any, *, roller) -> "CombatSession":
    """Every horse the shot was at, or landed near, rolls PRE or bolts."""
    from kirby_combat.nerve import FLED, HELD, modifiers
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import NerveRolled, make_author_engine
    from kirby_combat.wounds import _made, characteristic_roll_of
    from kirby_world.geometry import distance_3d
    from kirby_world.occupancy import position_of

    scene = getattr(session, "scene", None)
    aimed = position_of(scene, attack.target.id) if scene is not None else None
    for horse in _horses(session):
        if horse.id != attack.target.id:
            here = position_of(scene, horse.id) if scene is not None else None
            if aimed is None or here is None or distance_3d(here, aimed) > NEAR_M:
                continue
        mods = [(l, v) for l, v in modifiers(session, horse) if l != "unarmed"]
        needed = characteristic_roll_of(horse, "PRE") + sum(v for _l, v in mods)
        roll = sum(roller.roll_dice(3, 6))
        outcome = HELD if _made(roll, needed) else FLED
        session = apply_event(session, NerveRolled(
            id=str(uuid.uuid4()), session_id=session.id,
            sequence=len(session.event_log) + 1, timestamp=datetime.now(timezone.utc),
            author=make_author_engine(), combatant_id=horse.id, roll=roll,
            needed=needed, modifiers=tuple(f"{l}:{v:+d}" for l, v in mods),
            outcome=outcome))
    return session
