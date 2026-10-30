"""Knockback movement — Phase 1 KB integrated with Scene walls/edges/hazards.

Composes:
  - Phase 1 compute_knockback (distance + collision damage dice)
  - geometry.segments_intersect_xy (wall hit detection)
  - falling.is_supported_at + resolve_fall (edge falls)
  - hazards.compute_hazard_triggers (path-cross detection)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from kirby_combat.models import DiceValues
from kirby_combat.resolution.knockback import compute_knockback
from kirby_world.scene import Position, Scene, Wall
from kirby_world.geometry import segments_intersect_xy, segment_intersection_xy, wall_height_blocks
from kirby_world.falling import is_supported_at, resolve_fall, FallingResult
from kirby_world.hazards import compute_hazard_triggers, HazardTriggerResult

if TYPE_CHECKING:
    from kirby_combat.template import CombatTemplate


@dataclass(frozen=True)
class WallCollision:
    wall_id: str
    impact_position: Position
    distance_into_wall_m: float        # KB distance "lost" to the wall (target took collision damage from full KB)
    #: The structure's PD and BODY, which cap the impact dice (6E2 p.118:
    #: "the most dice of Knockback damage a character can take when he hits
    #: a structure equals the PD + BODY of the structure"). ``pd is None``
    #: is a wall authored with no DEF -- an indestructible one -- and the
    #: caller must decide what that caps at; it is not zero.
    pd: int | None
    body: int


@dataclass(frozen=True)
class KnockbackMovementResult:
    combatant_id: str
    intended_distance_m: float          # what Phase 1 calculated
    actual_distance_traveled_m: float   # what actually happened (less if wall stopped them)
    direction_xy: tuple[float, float]   # unit vector
    start_position: Position
    final_position: Position             # after collisions, falls, etc.
    wall_collision: WallCollision | None
    fall: FallingResult | None          # if KB pushed off an edge
    hazard_triggers: list[HazardTriggerResult]
    collision_damage_dice: int            # Phase 1's damage_dice — caller applies if there's a wall hit


@dataclass(frozen=True)
class ForcedMovement:
    """Where a body pushed ``distance_m`` along ``direction_xy`` ends up.

    The geometry knockback and a Throw share (6E2 p.118, p.84): the path
    stops at the first wall that blocks it, and a body that ends over
    nothing falls. ``travel_end`` is where the horizontal travel stopped,
    BEFORE any fall; ``fall`` is None when he is still standing on
    something (or is airborne and stays so).
    """
    start_position: Position
    travel_end: Position
    distance_traveled_m: float
    wall_collision: WallCollision | None
    fall: FallingResult | None
    hazard_triggers: list[HazardTriggerResult]

    @property
    def final_position(self) -> Position:
        return self.fall.landed_at if self.fall is not None else self.travel_end


def _unit_xy(from_pos: Position, to_pos: Position) -> tuple[float, float]:
    dx = to_pos.x - from_pos.x
    dy = to_pos.y - from_pos.y
    mag = math.hypot(dx, dy)
    if mag < 1e-9:
        return (1.0, 0.0)            # default east when no direction available
    return (dx / mag, dy / mag)


def _beyond(bounds, pos: Position) -> bool:
    return not (bounds.min_x <= pos.x <= bounds.max_x
                and bounds.min_y <= pos.y <= bounds.max_y)


def _just_inside(bounds, start: Position, end: Position) -> Position:
    """The point on the line from ``start`` to ``end``, a hair inside where it
    crosses the map's edge, at ``start``'s height."""
    from kirby_combat.off_board import _INSIDE_BY_M, exit_point

    ex, ey, _ = exit_point(bounds, {"x": start.x, "y": start.y, "z": start.z},
                           {"x": end.x, "y": end.y, "z": end.z})
    dx, dy = end.x - start.x, end.y - start.y
    mag = math.hypot(dx, dy) or 1.0
    return Position(x=ex - dx / mag * _INSIDE_BY_M, y=ey - dy / mag * _INSIDE_BY_M,
                    z=start.z, facing=start.facing)


def away_from(source: Position, body: Position) -> tuple[float, float]:
    """The unit direction straight away from ``source`` (6E2 p.118: "opposite
    the direction from which the attack came")."""
    return _unit_xy(source, body)


def resolve_forced_movement(
    *,
    combatant_id: str,
    start: Position,
    direction_xy: tuple[float, float],
    distance_m: float,
    scene: Scene,
    gravity_scale: float,
    airborne: bool,
) -> ForcedMovement:
    """Push a body ``distance_m`` along ``direction_xy`` through ``scene``.

    Walls and impermeable constructs stop it at the impact point. A body
    that ends unsupported FALLS -- unless it was ``airborne`` to begin
    with (a flyer), who is moved through the air and stays there: 6E2
    p.118, "If the character's so high up in the air that he hits nothing
    ... he takes no damage at all", and a flyer is able "to right himself
    and fly under his own power".
    """
    return resolve_forced_movement_past(
        combatant_id=combatant_id, start=start, direction_xy=direction_xy,
        distance_m=distance_m, scene=scene, gravity_scale=gravity_scale,
        airborne=airborne, passed_through=frozenset(),
    )


def resolve_forced_movement_past(
    *,
    combatant_id: str,
    start: Position,
    direction_xy: tuple[float, float],
    distance_m: float,
    scene: Scene,
    gravity_scale: float,
    airborne: bool,
    passed_through: frozenset[str],
) -> ForcedMovement:
    """`resolve_forced_movement`, ignoring the walls in ``passed_through``.

    A man Knocked Back through a structure he shattered "continues through
    the hole" (6E2 p.118): the next leg of his flight starts ON the wall he
    broke, and that wall must not stop him a second time. A breached face
    stays on the board (`collapse._breach`) and still blocks other movement,
    so it is named here rather than removed.
    """
    tentative_end = Position(
        x=start.x + direction_xy[0] * distance_m,
        y=start.y + direction_xy[1] * distance_m,
        z=start.z,
        facing=start.facing,
    )
    wall_collision: WallCollision | None = None
    actual_end = tentative_end
    actual_distance = distance_m

    _impermeable = [
        Wall(id=c.obj_id, name=c.obj_id, segment=c.segment, height_m=c.height_m,
             blocks_los=c.blocks_los, blocks_movement=True, cover_level=c.cover_level,
             body=(c.body if c.body is not None else 6),
             def_value=c.def_value)
        for c in (getattr(scene, "constructs", []) or [])
        if c.permeability == "impermeable" and c.segment is not None
    ]
    collision_walls = list(scene.walls) + _impermeable

    closest_dist = math.inf
    if distance_m > 0:
        for wall in collision_walls:
            if wall.id in passed_through:
                continue
            if not wall.blocks_movement:
                continue
            if not wall_height_blocks(start.z, wall):
                continue
            wa = (wall.segment[0].x, wall.segment[0].y)
            wb = (wall.segment[1].x, wall.segment[1].y)
            if not segments_intersect_xy(
                (start.x, start.y), (tentative_end.x, tentative_end.y), wa, wb,
            ):
                continue
            impact = segment_intersection_xy(
                (start.x, start.y), (tentative_end.x, tentative_end.y), wa, wb,
            )
            if impact is None:
                continue
            d = math.hypot(impact[0] - start.x, impact[1] - start.y)
            if d < closest_dist:
                closest_dist = d
                actual_end = Position(
                    x=impact[0], y=impact[1], z=start.z, facing=start.facing,
                )
                actual_distance = d
                wall_collision = WallCollision(
                    wall_id=wall.id,
                    impact_position=actual_end,
                    distance_into_wall_m=distance_m - d,
                    pd=wall.pd,
                    body=int(wall.body),
                )

    hazards = compute_hazard_triggers(
        scene=scene,
        combatant_positions_before={combatant_id: start},
        combatant_positions_after={combatant_id: actual_end},
        phase="movement",
    )

    # BEYOND THE EDGE THE GROUND GOES ON (Peter's ruling, 2026-10-29). Nothing
    # is authored past the map's bounds, so asking for support out there
    # found none and dropped him to `bounds.min_z` --- 5m down on the random
    # maps, a fall nobody took. The ground he lands on is the ground where
    # he crossed the edge: support is asked a hair inside it, and a fall
    # from there (a roof at the edge) lands at his landing point.
    # See `kirby_combat/off_board.py`.
    where_supported = actual_end
    if (wall_collision is None and not _beyond(scene.bounds, start)
            and _beyond(scene.bounds, actual_end)):
        where_supported = _just_inside(scene.bounds, start, actual_end)
    fall: FallingResult | None = None
    if not airborne and not is_supported_at(where_supported, scene):
        fall = resolve_fall(
            combatant_id=combatant_id,
            from_pos=where_supported,
            scene=scene,
            gravity_scale=gravity_scale,
        )
        if where_supported is not actual_end:
            fall = replace(fall, from_pos=actual_end, landed_at=Position(
                x=actual_end.x, y=actual_end.y, z=fall.landed_at.z,
                facing=actual_end.facing))
    return ForcedMovement(
        start_position=start, travel_end=actual_end,
        distance_traveled_m=actual_distance, wall_collision=wall_collision,
        fall=fall, hazard_triggers=hazards,
    )


def resolve_knockback_movement(
    *,
    combatant_id: str,
    attacker_pos: Position,
    target_pos: Position,
    body_dealt: int,
    kb_resistance: int,
    dice: DiceValues,
    scene: Scene,
    template: "CombatTemplate",
    gravity_scale: float = 1.0,
) -> KnockbackMovementResult:
    # 1. Phase 1 KB calc — per 6E2 p116, KB-roll is 2d6 (+ modifier dice)
    # subtracted from BODY. Caller passes dice.knockback as the rolled pool.
    kb = compute_knockback(
        body=body_dealt,
        knockback_dice=list(dice.knockback),
        kb_resistance_m=kb_resistance,
        template=template,
    )
    intended = kb.distance_m
    collision_damage = kb.damage_dice

    # 2. Direction
    direction = _unit_xy(attacker_pos, target_pos)

    # 3. Resisted? Short-circuit.
    if intended <= 0:
        return KnockbackMovementResult(
            combatant_id=combatant_id,
            intended_distance_m=0.0,
            actual_distance_traveled_m=0.0,
            direction_xy=direction,
            start_position=target_pos,
            final_position=target_pos,
            wall_collision=None,
            fall=None,
            hazard_triggers=[],
            collision_damage_dice=collision_damage,
        )

    # 4-7. Walls, hazards and the edge: the geometry a Throw shares.
    moved = resolve_forced_movement(
        combatant_id=combatant_id, start=target_pos, direction_xy=direction,
        distance_m=intended, scene=scene, gravity_scale=gravity_scale,
        airborne=False,
    )
    wall_collision = moved.wall_collision
    actual_distance = moved.distance_traveled_m
    fall = moved.fall
    final_pos = moved.final_position
    hazards = moved.hazard_triggers

    return KnockbackMovementResult(
        combatant_id=combatant_id,
        intended_distance_m=intended,
        actual_distance_traveled_m=actual_distance,
        direction_xy=direction,
        start_position=target_pos,
        final_position=final_pos,
        wall_collision=wall_collision,
        fall=fall,
        hazard_triggers=hazards,
        collision_damage_dice=collision_damage,
    )
