"""Close-and-strike — the half-move-then-attack composite.

Sits beside `move_by.py` and `move_through.py`, which are the same shape: a
pure calculator that decides what the rules permit and leaves persistence,
dice and event emission to the caller.

What it settles, in order:

1. **The close.** Resolved through `movement_reach`, so per-mode legality
   holds — running is same-elevation only, leaping has a vertical capacity,
   flight is free 3D. `movement_reach` CLAMPS: an illegal or over-long move
   lands the actor short rather than failing loudly, and it reports a REFUSED
   move (an unmodelled mode, a mode that cannot operate here, a Stunned
   combatant who may not move at all) as `reachable=False` with the landing
   back at the start.
2. **Reach (6E2 p36, 6E2 p56).** Measured at the landing position, never at
   the position the action was chosen from. This is the check whose absence
   let a martial throw resolve between combatants separated by six metres of
   elevation.
3. **The refusal.** Landing in reach is not enough: the close must also have
   been ALLOWED. Without this an actor who already stands adjacent gets a free
   strike out of a mode that was refused outright — swimming on dry land, a
   mode this engine does not model, or a Stunned combatant, whose refusal
   `movement_reach` reports the same way.
4. **Perception.** An attacker who closed but still cannot perceive the target
   does not land a clean full-CV blow; adjacent-but-unperceived strikes blind
   (6E2 p9, restated on p127: ½ OCV and ½ DCV in HTH when no Targeting
   Sense reaches the opponent). This is
   the anti-metagaming gate, preserved from the kirby-api implementation this
   module replaces.

Reach before perception is deliberate: an attacker who never arrived has no
attack to gate, and "unperceived" would describe the wrong failure. The
refusal sits between them because it only ever bites when the reach test has
already passed — that is precisely the already-adjacent case.

**The mid-air retry.** The close aims at a point one Reach short of the
target, which for an elevated target hangs in mid-air. Modes that must finish
on a supported surface (teleportation among them) cannot accept such a
destination, so when the short-of point is refused or lands out of reach the
close is retried at the target's OWN position, which is supported by
construction. Carried over from kirby-api, where a teleporter that could
legally arrive adjacent was otherwise told it could not.

**The scene-less path is an approximation.** With `scene=None` there is no
geometry to consult, so the close is a straight line clamped to the movement
budget and `mode` is IGNORED — no elevation rule, no walls, no support, no
refusal. A running actor will happily "close" straight down a six-metre drop.
Only the reach rule still bites. Pass a scene whenever mode legality matters.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Optional

from kirby_combat.actions.reach import ReachVerdict, within_reach
from kirby_combat.scene.geometry import distance_3d
from kirby_combat.scene.scene import Position


@dataclass(frozen=True)
class StrikePlan:
    """The attack the caller should now resolve.

    `blind` ⇒ the target was closed to but is still unperceived: resolve at
    ½ OCV / ½ DCV (6E2 p9, p127) rather than full CV.
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
    reason: str          # "" when striking; else "out_of_reach" | "move_refused" | "fell"


def _point_short_of(actor: Position, target: Position, reach_m: float) -> Position:
    """A point on the actor→target line sitting `reach_m` short of the target,
    so a mover landing there is exactly within reach.

    Returns the ACTOR's own position when the target is already inside reach:
    there is nothing to close, and walking on toward an adjacent enemy would
    put the two combatants in the same square.
    """
    d = distance_3d(actor, target)
    if d <= reach_m:
        return actor
    frac = (d - reach_m) / d
    return Position(
        x=actor.x + (target.x - actor.x) * frac,
        y=actor.y + (target.y - actor.y) * frac,
        z=actor.z + (target.z - actor.z) * frac,
        facing=actor.facing,
    )


def _arrives(landing: Position, target_pos: Position, reach_m: float) -> bool:
    return within_reach(distance_3d(landing, target_pos), reach_m).in_reach


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
    desired = _point_short_of(actor_pos, target_pos, reach_m)

    fell = False
    refused = False
    if scene is None:
        # Scene-less: a straight-line close, clamped to the budget. See the
        # module docstring — `mode` is not consulted on this path.
        d_full = distance_3d(actor_pos, desired)
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
        if not (outcome.reachable and _arrives(outcome.landing, target_pos, reach_m)):
            # The mid-air retry: aim at the target's own (supported) square.
            #
            # This deliberately accepts CO-LOCATION, which `_point_short_of`
            # refuses on the ordinary path. The two are not in conflict: on
            # the ordinary path stopping one Reach short is available and is
            # simply better, whereas the retry only ever runs BECAUSE that
            # point cannot be landed on — the target's own square is then the
            # only arrival the mode allows, and a teleporter that can legally
            # get there should not be told it cannot. The caller resolves the
            # overlap (shove, share the hex, GM call); this module reports the
            # landing it computed and does not invent a nearby one.
            retry = movement_reach(
                mode, actor_pos, target_pos, half_move_m, scene,
                combatant_id=actor_id, session=session,
            )
            if retry.reachable and _arrives(retry.landing, target_pos, reach_m):
                outcome = retry
        landing = outcome.landing
        fell = outcome.fall is not None
        refused = not outcome.reachable

    travelled = distance_3d(actor_pos, landing)
    distance_after = distance_3d(landing, target_pos)
    verdict = within_reach(distance_after, reach_m)

    def _no_strike(reason: str) -> MoveStrikeOutcome:
        return MoveStrikeOutcome(
            landing=landing, travelled_m=travelled,
            distance_after_m=distance_after, reach=verdict, fell=fell,
            strike=None, reason=reason,
        )

    if not verdict.in_reach:
        return _no_strike("out_of_reach")

    if refused:
        # In reach, but only because the actor never had to move. The mode
        # refused the close outright, so there is no half-move-and-strike to
        # be had out of standing still.
        return _no_strike("move_refused")

    if fell:
        # Landed in reach but fell getting there: the phase is spent on the
        # fall, not on a punch.
        return _no_strike("fell")

    blind = False
    if scene is not None and observer is not None and target is not None:
        from kirby_combat.perception import perceive

        perc = perceive(
            observer, target, _scene_after_close(scene, observer.id, landing),
            target_invisible=target_invisible, target_hidden=target_hidden,
            roller=roller,
        )
        # Read the flags directly: a renamed field must break loudly here
        # rather than degrade every strike in the game to a blind one.
        perceivable = bool(perc.targetable_physical or perc.targetable_mental)
        # In reach but unperceived ⇒ the blow may land, blind. (Out of reach
        # was already returned above, so there is no unperceived-and-distant
        # case to consider here.)
        blind = not perceivable

    return MoveStrikeOutcome(
        landing=landing, travelled_m=travelled,
        distance_after_m=distance_after, reach=verdict, fell=False,
        strike=StrikePlan(blind=blind), reason="",
    )


def _scene_after_close(scene: Any, observer_id: str, landing: Position) -> Any:
    """The scene as perception should see it: the mover standing where the
    close actually left it.

    Perception is range- and line-of-sight-sensitive, so consulting it against
    the PRE-close position would judge the wrong geometry. Returns a NEW scene
    (this module mutates nothing), and only when the scene already tracks this
    combatant — inventing a position for an untracked one would change what
    `perceive` measures rather than correct it.

    Keyed on the OBSERVER's id, because that is the id `perceive` looks the
    position up under. `actor_id` is the movement key (what `movement_reach`
    threads to a fall), and the two need not be the same string — writing the
    landing under `actor_id` would silently restore the stale-position bug
    this helper exists to fix whenever a caller's two ids differ.
    """
    positions = getattr(scene, "combatant_positions", None)
    if not positions or observer_id not in positions:
        return scene
    return replace(
        scene, combatant_positions={**positions, observer_id: landing},
    )
