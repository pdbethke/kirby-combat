"""movement_reach — per-mode movement legality + vertical physics + fall.

Pure resolver (Scene + Positions in, MovementOutcome out) for the movement
spec §2. Given a movement `mode`, a `from_pos`/`to_pos`, and the mode's
`distance_m` capacity, decides whether `to_pos` is reachable, what the actual
landing position is (clamped to what the mode/distance achieves toward the
target), and whether the landing triggers a fall.

Per-mode rules (spec §2 / Decisions §3):
  - running       same-elevation only; blocked by impermeable walls crossing the
                  path; lands short at the wall; falls off an unsupported ledge.
  - leaping       horizontal up to distance_m, vertical up to distance_m/2;
                  clears a wall whose top (relative to the start) is within the
                  leap's vertical capacity; falls if the landing is unsupported.
  - flight        free 3D within range, up to the scene ceiling; over walls; no
                  fall (sustained).
  - teleportation any *supported* destination within range; ignores walls (no
                  path); no fall.
  - swimming      only toward/within a water surface; otherwise unavailable.
  - tunneling     v1 simple — same/ground elevation within range (material-DEF
                  deferred).

Reuses `scene/falling.py` (`is_supported_at`, `resolve_fall`) and the wall
geometry helpers from `scene/geometry.py` (`segment_intersection_xy`,
`wall_height_blocks`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from kirby_combat.scene.scene import Position, Scene, Wall
from kirby_combat.scene.geometry import (
    distance_3d,
    point_in_polygon_xy,
    segments_intersect_xy,
    segment_intersection_xy,
    wall_height_blocks,
)
from kirby_combat.scene.falling import is_supported_at, resolve_fall, FallingResult

_EPS = 1e-6
_FALL_COMBATANT_ID = "mover"   # default; overridden by movement_reach(combatant_id=)

# How close (xy, metres) a destination must be to a wall's segment to count as
# "on that face". A climber hugs the wall; this is not a reach radius.
CLIMB_FACE_REACH_M = 1.0

# Modes that sustain themselves in mid-air. `_flight` never falls and can
# hold a position with nothing underneath it; nothing else can.
_HOVERING_MODES = frozenset({"flight"})


def mode_requires_support(mode: str) -> bool:
    """Does `mode` need a supporting surface under its destination?

    False for ``"flight"`` alone. True for running, leaping, teleportation,
    tunneling and swimming — swimming additionally keeps its own
    ``_point_in_water`` gate. An unknown mode conservatively requires
    support: we never propose a mid-air destination for a mode we do not
    model.
    """
    return mode not in _HOVERING_MODES


@dataclass
class MovementOutcome:
    reachable: bool
    landing: Position
    fall: "FallingResult | None" = None


def _xy_distance(a: Position, b: Position) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def _clamp_xy_toward(from_pos: Position, to_pos: Position, max_d: float) -> Position:
    """Point along the from→to xy ray clamped to `max_d` (xy distance), keeping
    to_pos.z. If already within `max_d`, returns `to_pos`."""
    d = _xy_distance(from_pos, to_pos)
    if d <= max_d + _EPS or d < _EPS:
        return to_pos
    frac = max_d / d
    return Position(
        x=from_pos.x + (to_pos.x - from_pos.x) * frac,
        y=from_pos.y + (to_pos.y - from_pos.y) * frac,
        z=to_pos.z,
        facing=to_pos.facing,
    )


def _first_blocking_wall_xy(
    from_pos: Position, to_pos: Position, scene: Scene, target_z: float,
) -> tuple[Wall, Position] | None:
    """Nearest movement-blocking wall whose vertical extent covers `target_z`
    and whose segment crosses the from→to xy path. Returns (wall, impact_pos)
    where impact_pos is the xy intersection at `target_z`, or None."""
    closest: tuple[Wall, Position] | None = None
    closest_dist = math.inf
    for wall in scene.walls:
        if not wall.blocks_movement:
            continue
        if not wall_height_blocks(target_z, wall):
            continue
        wa = (wall.segment[0].x, wall.segment[0].y)
        wb = (wall.segment[1].x, wall.segment[1].y)
        if not segments_intersect_xy(
            (from_pos.x, from_pos.y), (to_pos.x, to_pos.y), wa, wb
        ):
            continue
        impact = segment_intersection_xy(
            (from_pos.x, from_pos.y), (to_pos.x, to_pos.y), wa, wb
        )
        if impact is None:
            continue
        d = math.hypot(impact[0] - from_pos.x, impact[1] - from_pos.y)
        if d < closest_dist:
            closest_dist = d
            impact_pos = Position(
                x=impact[0], y=impact[1], z=target_z, facing=from_pos.facing
            )
            closest = (wall, impact_pos)
    return closest


def _maybe_fall(
    landing: Position, scene: Scene, combatant_id: str = _FALL_COMBATANT_ID
) -> "FallingResult | None":
    if is_supported_at(landing, scene):
        return None
    return resolve_fall(
        combatant_id=combatant_id,
        from_pos=landing,
        scene=scene,
        gravity_scale=scene.ambient.gravity_scale,
    )


def _point_in_water(pos: Position, scene: Scene) -> bool:
    for surf in scene.surfaces:
        if surf.surface_type != "water":
            continue
        if abs(surf.elevation_m - pos.z) > _EPS:
            continue
        if point_in_polygon_xy((pos.x, pos.y), surf.polygon_xy):
            return True
    return False


def movement_reach(
    mode: str,
    from_pos: Position,
    to_pos: Position,
    distance_m: float,
    scene: Scene,
    combatant_id: str = "mover",
) -> MovementOutcome:
    """Resolve whether `to_pos` is reachable from `from_pos` via `mode` with
    `distance_m` of movement capacity. Returns a MovementOutcome with the actual
    landing position and any resulting fall.

    `combatant_id` is threaded to `resolve_fall` so that callers consuming
    `MovementOutcome.fall` can treat `fall.combatant_id` as the mover's id.
    Defaults to ``"mover"`` so existing call sites without the argument are
    unaffected.
    """
    if mode == "running":
        return _running(from_pos, to_pos, distance_m, scene, combatant_id)
    if mode == "leaping":
        return _leaping(from_pos, to_pos, distance_m, scene, combatant_id)
    if mode == "flight":
        return _flight(from_pos, to_pos, distance_m, scene)
    if mode == "teleportation":
        return _teleportation(from_pos, to_pos, distance_m, scene)
    if mode == "swimming":
        return _swimming(from_pos, to_pos, distance_m, scene)
    if mode == "tunneling":
        return _tunneling(from_pos, to_pos, distance_m, scene)
    if mode == "climbing":
        return _climbing(from_pos, to_pos, distance_m, scene)
    return MovementOutcome(reachable=False, landing=from_pos, fall=None)


def _running(
    from_pos: Position, to_pos: Position, distance_m: float, scene: Scene,
    combatant_id: str = _FALL_COMBATANT_ID,
) -> MovementOutcome:
    same_z = abs(to_pos.z - from_pos.z) <= _EPS

    # A blocking wall crossing the path stops the run at the wall — regardless of
    # elevation legality (you physically can't reach across it).
    blocker = _first_blocking_wall_xy(from_pos, to_pos, scene, from_pos.z)
    if blocker is not None:
        wall, impact = blocker
        dist_to_wall = _xy_distance(from_pos, impact)
        if dist_to_wall <= distance_m + _EPS:
            # Stop just before the wall (clamp to within reach if the wall is
            # farther than we can run anyway).
            landing = impact if dist_to_wall <= distance_m else \
                _clamp_xy_toward(from_pos, impact, distance_m)
            return MovementOutcome(
                reachable=False, landing=landing,
                fall=_maybe_fall(landing, scene, combatant_id),
            )
        # Wall is beyond our reach; fall through to the clamp-to-distance path.

    if not same_z:
        # Running can't change elevation. Clamp toward the target in xy (at the
        # start's z) and report unreachable.
        landing = _clamp_xy_toward(from_pos, to_pos, distance_m)
        landing = Position(landing.x, landing.y, from_pos.z, landing.facing)
        return MovementOutcome(
            reachable=False, landing=landing,
            fall=_maybe_fall(landing, scene, combatant_id),
        )

    # Same elevation, unblocked: reach if within distance, else clamp short.
    d3 = distance_3d(from_pos, to_pos)
    if d3 <= distance_m + _EPS:
        landing = to_pos
        reachable = True
    else:
        landing = _clamp_xy_toward(from_pos, to_pos, distance_m)
        reachable = False
    return MovementOutcome(
        reachable=reachable, landing=landing,
        fall=_maybe_fall(landing, scene, combatant_id),
    )


def _leaping(
    from_pos: Position, to_pos: Position, distance_m: float, scene: Scene,
    combatant_id: str = _FALL_COMBATANT_ID,
) -> MovementOutcome:
    horizontal_cap = distance_m
    vertical_cap = distance_m / 2.0

    horiz = _xy_distance(from_pos, to_pos)
    rise = to_pos.z - from_pos.z

    # A wall blocks the leap only if (wall_base_z + wall.height_m - from_pos.z),
    # i.e. the wall top's height above the leaper's start, exceeds vertical_cap.
    # If it does not, the leap arc clears it.
    wall_clears = True
    for wall in scene.walls:
        if not wall.blocks_movement:
            continue
        wa = (wall.segment[0].x, wall.segment[0].y)
        wb = (wall.segment[1].x, wall.segment[1].y)
        if not segments_intersect_xy(
            (from_pos.x, from_pos.y), (to_pos.x, to_pos.y), wa, wb
        ):
            continue
        wall_base_z = min(wall.segment[0].z, wall.segment[1].z)
        wall_top_z = wall_base_z + wall.height_m
        if (wall_top_z - from_pos.z) > vertical_cap + _EPS:
            wall_clears = False
            break

    reachable = (
        horiz <= horizontal_cap + _EPS
        and rise <= vertical_cap + _EPS
        and wall_clears
    )

    if reachable:
        landing = to_pos
    else:
        # Clamp horizontally toward the target (overshoot short of it).
        landing = _clamp_xy_toward(from_pos, to_pos, horizontal_cap)

    return MovementOutcome(
        reachable=reachable, landing=landing,
        fall=_maybe_fall(landing, scene, combatant_id),
    )


def _flight(
    from_pos: Position, to_pos: Position, distance_m: float, scene: Scene
) -> MovementOutcome:
    d3 = distance_3d(from_pos, to_pos)
    reachable = (
        d3 <= distance_m + _EPS
        and to_pos.z <= scene.bounds.max_z + _EPS
    )
    # Flight is sustained — it never falls. Landing is the target when reachable,
    # else clamped toward it (3D) at the ceiling-limited point.
    if reachable:
        landing = to_pos
    else:
        landing = _flight_clamp(from_pos, to_pos, distance_m, scene)
    return MovementOutcome(reachable=reachable, landing=landing, fall=None)


def _flight_clamp(
    from_pos: Position, to_pos: Position, distance_m: float, scene: Scene
) -> Position:
    d3 = distance_3d(from_pos, to_pos)
    if d3 < _EPS:
        return to_pos
    frac = min(1.0, distance_m / d3)
    z = from_pos.z + (to_pos.z - from_pos.z) * frac
    z = min(z, scene.bounds.max_z)
    return Position(
        x=from_pos.x + (to_pos.x - from_pos.x) * frac,
        y=from_pos.y + (to_pos.y - from_pos.y) * frac,
        z=z,
        facing=to_pos.facing,
    )


def _teleportation(
    from_pos: Position, to_pos: Position, distance_m: float, scene: Scene
) -> MovementOutcome:
    d3 = distance_3d(from_pos, to_pos)
    reachable = d3 <= distance_m + _EPS and is_supported_at(to_pos, scene)
    # No path → ignores walls; either lands at the supported target or doesn't go.
    landing = to_pos if reachable else from_pos
    return MovementOutcome(reachable=reachable, landing=landing, fall=None)


def _swimming(
    from_pos: Position, to_pos: Position, distance_m: float, scene: Scene
) -> MovementOutcome:
    d3 = distance_3d(from_pos, to_pos)
    reachable = d3 <= distance_m + _EPS and _point_in_water(to_pos, scene)
    landing = to_pos if reachable else from_pos
    return MovementOutcome(reachable=reachable, landing=landing, fall=None)


def _tunneling(
    from_pos: Position, to_pos: Position, distance_m: float, scene: Scene
) -> MovementOutcome:
    # v1 simple ground gate: same elevation, within range. Material-DEF deferred.
    same_z = abs(to_pos.z - from_pos.z) <= _EPS
    d3 = distance_3d(from_pos, to_pos)
    reachable = same_z and d3 <= distance_m + _EPS
    landing = to_pos if reachable else from_pos
    return MovementOutcome(reachable=reachable, landing=landing, fall=None)


def _climbing(
    from_pos: Position, to_pos: Position, distance_m: float, scene: Scene
) -> MovementOutcome:
    """Climbing (6E1 p70). Legal only ON a climbable face: within
    ``CLIMB_FACE_REACH_M`` of a climbable wall's segment in xy, and at a z
    between that wall's base and its top INCLUSIVE — the top is where the
    walkable strip is, and reaching it is the point.

    Deliberately never calls ``_maybe_fall``. A climber partway up a face is
    over open air by the support model; whether they fall is governed by the
    consumer's ``climbing:`` status (a failed roll, a Stun, knockback), not by
    geometry. Falling here would drop every climber on their first metre.
    """
    from kirby_combat.scene.scene import is_climbable

    d3 = distance_3d(from_pos, to_pos)
    if d3 > distance_m + _EPS:
        return MovementOutcome(reachable=False, landing=from_pos, fall=None)

    for wall in scene.walls:
        if not is_climbable(wall):
            continue
        a, b = wall.segment
        near = _nearest_point_on_segment_xy(
            to_pos.x, to_pos.y, a.x, a.y, b.x, b.y,
        )
        if math.hypot(near[0] - to_pos.x, near[1] - to_pos.y) > CLIMB_FACE_REACH_M:
            continue
        base = min(a.z, b.z)
        if base - _EPS <= to_pos.z <= base + wall.height_m + _EPS:
            return MovementOutcome(reachable=True, landing=to_pos, fall=None)

    return MovementOutcome(reachable=False, landing=from_pos, fall=None)


def _nearest_point_on_segment_xy(
    px: float, py: float, ax: float, ay: float, bx: float, by: float,
) -> tuple[float, float]:
    """Closest point to (px, py) on segment ab, in xy."""
    dx, dy = bx - ax, by - ay
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return (ax, ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len_sq))
    return (ax + t * dx, ay + t * dy)
