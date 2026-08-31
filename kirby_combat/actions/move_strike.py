"""Close-and-strike — the half-move-then-attack composite.

Sits beside `move_by.py` and `move_through.py`, which are the same shape: a
pure calculator that decides what the rules permit and leaves persistence,
dice and event emission to the caller.

What it settles, in order:

1. **The close.** Resolved through `movement_reach`, so per-mode legality
   holds — running is same-elevation only, leaping has a vertical capacity,
   flight is free 3D. `movement_reach` CLAMPS: an illegal or over-long move
   lands the actor short rather than failing loudly.
2. **Reach (6E2 p36, 6E2 p56).** Measured at the landing position, never at
   the position the action was chosen from. This is the check whose absence
   let a martial throw resolve between combatants separated by six metres of
   elevation.
3. **Perception.** An attacker who closed but still cannot perceive the target
   does not land a clean full-CV blow; adjacent-but-unperceived strikes blind
   (½ OCV / ½ DCV). This is the anti-metagaming gate, preserved from the
   kirby-api implementation this module replaces.

Reach before perception is deliberate: an attacker who never arrived has no
attack to gate, and "unperceived" would describe the wrong failure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from kirby_combat.actions.reach import ReachVerdict, within_reach
from kirby_combat.scene.scene import Position


@dataclass(frozen=True)
class StrikePlan:
    """The attack the caller should now resolve.

    `blind` ⇒ the target was closed to but is still unperceived: resolve at
    ½ OCV / ½ DCV rather than full CV.
    """

    blind: bool


@dataclass(frozen=True)
class MoveStrikeOutcome:
    landing: Position
    travelled_m: float
    distance_after_m: float
    reach: ReachVerdict
    fell: bool
    strike: Optional[StrikePlan]
    reason: str          # "" when striking; else "out_of_reach" | "unperceived" | "fell"


def _distance(a: Position, b: Position) -> float:
    return math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 + (b.z - a.z) ** 2)


def _point_short_of(target: Position, actor: Position, reach_m: float) -> Position:
    """A point on the actor→target line sitting `reach_m` short of the target,
    so a mover landing there is exactly within reach. Returns the target's own
    position when already inside reach (nothing to close)."""
    d = _distance(actor, target)
    if d <= reach_m or d <= 0.0:
        return target
    frac = (d - reach_m) / d
    return Position(
        x=actor.x + (target.x - actor.x) * frac,
        y=actor.y + (target.y - actor.y) * frac,
        z=actor.z + (target.z - actor.z) * frac,
        facing=actor.facing,
    )


def resolve_move_strike(
    *,
    scene: Any | None,
    actor_pos: Position,
    target_pos: Position,
    mode: str,
    half_move_m: float,
    reach_m: float,
    actor_id: str = "mover",
    observer: Any | None = None,
    target: Any | None = None,
    target_invisible: bool = False,
    target_hidden: bool = False,
    roller: Any | None = None,
    session: Any | None = None,
) -> MoveStrikeOutcome:
    """Close toward `target_pos`, then decide whether a HTH strike may happen.

    `observer` / `target` are the engine-shaped combatants the perception gate
    needs. Omit them (or omit `scene`) and perception is not consulted — the
    reach rule still is.
    """
    desired = _point_short_of(target_pos, actor_pos, reach_m)

    fell = False
    if scene is None:
        # Scene-less: a straight-line close, clamped to the budget.
        d_full = _distance(actor_pos, desired)
        if d_full <= half_move_m or d_full <= 0.0:
            landing = desired
        else:
            frac = half_move_m / d_full
            landing = Position(
                x=actor_pos.x + (desired.x - actor_pos.x) * frac,
                y=actor_pos.y + (desired.y - actor_pos.y) * frac,
                z=actor_pos.z + (desired.z - actor_pos.z) * frac,
                facing=actor_pos.facing,
            )
    else:
        from kirby_combat.scene.movement_legality import movement_reach

        outcome = movement_reach(
            mode, actor_pos, desired, half_move_m, scene,
            combatant_id=actor_id, session=session,
        )
        landing = outcome.landing
        fell = outcome.fall is not None

    travelled = _distance(actor_pos, landing)
    distance_after = _distance(landing, target_pos)
    verdict = within_reach(distance_after, reach_m)

    if not verdict.in_reach:
        return MoveStrikeOutcome(
            landing=landing, travelled_m=travelled,
            distance_after_m=distance_after, reach=verdict, fell=fell,
            strike=None, reason="out_of_reach",
        )

    if fell:
        # Landed in reach but fell getting there: the phase is spent on the
        # fall, not on a punch.
        return MoveStrikeOutcome(
            landing=landing, travelled_m=travelled,
            distance_after_m=distance_after, reach=verdict, fell=True,
            strike=None, reason="fell",
        )

    blind = False
    if scene is not None and observer is not None and target is not None:
        from kirby_combat.perception import perceive

        perc = perceive(
            observer, target, scene,
            target_invisible=target_invisible, target_hidden=target_hidden,
            roller=roller,
        )
        perceivable = bool(
            getattr(perc, "targetable_physical", False)
            or getattr(perc, "targetable_mental", False)
        )
        # In reach but unperceived ⇒ the blow may land, blind. (Out of reach
        # was already returned above, so there is no unperceived-and-distant
        # case to consider here.)
        blind = not perceivable

    return MoveStrikeOutcome(
        landing=landing, travelled_m=travelled,
        distance_after_m=distance_after, reach=verdict, fell=False,
        strike=StrikePlan(blind=blind), reason="",
    )
