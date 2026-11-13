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

`closes_on` asks the next question: does the move END within his reach of
that enemy (6E2 p.56)? It is the one copy, used by the Move By gate, the
page's reach lines and a seat weighing a Multipower split.
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


class NoGeometry(ValueError):
    """`closes_on` was asked about a fight it cannot see: no Scene, or the
    mover or the enemy is not on it. Raised rather than answered, because
    either answer would be a guess."""


def closes_on(
    scene: Scene | None,
    mover_id: str,
    target_id: str,
    *,
    mode: str,
    budget_m: float,
    reach_m: float,
    session: CombatSession | None,
) -> bool:
    """Can ``mover_id``, moving ``budget_m`` by ``mode``, END within
    ``reach_m`` of ``target_id`` this Phase?

    THE ONE COPY of the question. The place says where the move lands
    (`movement_reach`, refused for a Stunned mover when ``session`` is
    given) and the landing is held to his reach (`within_reach`, 6E2 p.56):
    a move that arrives but stops out of reach does not close. The Move By /
    Move Through gate (`martial_offers.charge_connects`, 6E2 p.72) is its
    Running case, the page's "reaches him this Phase" its other modes, and a
    seat weighing a Multipower split asks it of a slot's movement.

    NO GEOMETRY IS NOT AN ANSWER: a missing Scene or a mover or enemy not on
    it raises `NoGeometry`. A caller with its own contract for that case
    (the menu's gates, which do not gate what they cannot judge) checks the
    positions itself before asking.
    """
    from kirby_world.geometry import distance_3d

    from kirby_combat.actions.reach import within_reach

    positions = (getattr(scene, "combatant_positions", None) or {}) if scene is not None else {}
    here, there = positions.get(mover_id), positions.get(target_id)
    if scene is None or here is None or there is None:
        raise NoGeometry(
            f"cannot say whether {mover_id!r} closes on {target_id!r}: "
            + ("there is no Scene" if scene is None else
               f"{mover_id if here is None else target_id!r} is not on the Scene"))
    if budget_m <= 0.0:
        return False
    can_move = session is None or not stunned_or_recovering_for(session, mover_id)
    out = _place_reach(mode, here, there, budget_m, scene,
                       combatant_id=mover_id, mover_can_move=can_move)
    return bool(out.reachable) and within_reach(distance_3d(out.landing, there),
                                                reach_m).in_reach
