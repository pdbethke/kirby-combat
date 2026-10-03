"""Where a combatant in a fight can get to: the place's answer, asked by
someone who knows whether he can move at all.

`kirby_world.movement_legality.movement_reach` answers for the place --- walls,
supports, reach, falls. Whether the mover may move at all is a rule about the
MOVER: a character who is Stunned or recovering from being Stunned cannot move
(6E2 p.106). That question needs the fight, so it is asked here and handed to
the world as `mover_can_move`.

Same signature as the function this used to be, `session` included, so every
caller --- and anyone importing it from `kirby_combat.scene.movement_legality`
--- keeps working unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kirby_world.movement_legality import MovementOutcome
from kirby_world.movement_legality import movement_reach as _place_reach

from kirby_combat.statuses import stunned_or_recovering_for

if TYPE_CHECKING:
    from kirby_world.scene import Position, Scene

    from kirby_combat.session.combat_session import CombatSession


def movement_reach(
    mode: str,
    from_pos: Position,
    to_pos: Position,
    distance_m: float,
    scene: Scene,
    combatant_id: str = "mover",
    session: CombatSession | None = None,
    teleport_ap_levels: int = 0,
) -> MovementOutcome:
    """`kirby_world`'s `movement_reach`, refused outright for a mover who is
    Stunned or recovering in `session`. With no session, exactly the place's
    answer --- no Stunned check, as before."""
    can_move = session is None or not stunned_or_recovering_for(session, combatant_id)
    return _place_reach(
        mode, from_pos, to_pos, distance_m, scene,
        combatant_id=combatant_id, mover_can_move=can_move,
        teleport_ap_levels=teleport_ap_levels,
    )
