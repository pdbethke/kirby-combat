"""Knockback movement — Phase 1 KB integrated with Scene walls/edges/hazards.

Composes:
  - Phase 1 compute_knockback (distance + collision damage dice)
  - geometry.segments_intersect_xy (wall hit detection)
  - falling.is_supported_at + resolve_fall (edge falls)
  - hazards.compute_hazard_triggers (path-cross detection)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from kirby_combat.models import DiceValues
from kirby_combat.resolution.knockback import compute_knockback
from kirby_combat.scene.scene import Position, Scene, Wall
from kirby_combat.scene.geometry import segments_intersect_xy
from kirby_combat.scene.falling import is_supported_at, resolve_fall, FallingResult
from kirby_combat.scene.hazards import compute_hazard_triggers, HazardTriggerResult

if TYPE_CHECKING:
    from kirby_combat.template import CombatTemplate


@dataclass(frozen=True)
class WallCollision:
    wall_id: str
    impact_position: Position
    distance_into_wall_m: float        # KB distance "lost" to the wall (target took collision damage from full KB)


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


def _unit_xy(from_pos: Position, to_pos: Position) -> tuple[float, float]:
    dx = to_pos.x - from_pos.x
    dy = to_pos.y - from_pos.y
    mag = math.hypot(dx, dy)
    if mag < 1e-9:
        return (1.0, 0.0)            # default east when no direction available
    return (dx / mag, dy / mag)


def _segment_intersection_xy(
    a1: tuple[float, float], a2: tuple[float, float],
    b1: tuple[float, float], b2: tuple[float, float],
) -> tuple[float, float] | None:
    """Compute the (x, y) intersection point of two segments, or None if parallel/no intersection."""
    x1, y1 = a1
    x2, y2 = a2
    x3, y3 = b1
    x4, y4 = b2
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None     # parallel
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def _wall_height_blocks(target_z: float, wall: Wall) -> bool:
    """True if the wall's vertical extent covers target_z."""
    base = min(wall.segment[0].z, wall.segment[1].z)
    top = base + wall.height_m
    return base <= target_z <= top


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
        knockback_multiplier=template.knockback_multiplier,
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

    # 4. Tentative end (xy at target_pos.z)
    tentative_end = Position(
        x=target_pos.x + direction[0] * intended,
        y=target_pos.y + direction[1] * intended,
        z=target_pos.z,
        facing=target_pos.facing,
    )

    # 5. Wall collisions — find the nearest wall that blocks the KB path
    wall_collision: WallCollision | None = None
    actual_end = tentative_end
    actual_distance = intended

    _impermeable = [
        Wall(id=c.obj_id, name=c.obj_id, segment=c.segment, height_m=c.height_m,
             blocks_los=c.blocks_los, blocks_movement=True, cover_level=c.cover_level,
             body=(c.body if c.body is not None else 6))
        for c in (getattr(scene, "constructs", []) or [])
        if c.permeability == "impermeable" and c.segment is not None
    ]
    collision_walls = list(scene.walls) + _impermeable

    closest_dist = math.inf
    for wall in collision_walls:
        if not wall.blocks_movement:
            continue
        if not _wall_height_blocks(target_pos.z, wall):
            continue
        wa = (wall.segment[0].x, wall.segment[0].y)
        wb = (wall.segment[1].x, wall.segment[1].y)
        if not segments_intersect_xy(
            (target_pos.x, target_pos.y),
            (tentative_end.x, tentative_end.y),
            wa, wb,
        ):
            continue
        impact = _segment_intersection_xy(
            (target_pos.x, target_pos.y),
            (tentative_end.x, tentative_end.y),
            wa, wb,
        )
        if impact is None:
            continue
        d = math.hypot(impact[0] - target_pos.x, impact[1] - target_pos.y)
        if d < closest_dist:
            closest_dist = d
            actual_end = Position(
                x=impact[0], y=impact[1], z=target_pos.z, facing=target_pos.facing,
            )
            actual_distance = d
            wall_collision = WallCollision(
                wall_id=wall.id,
                impact_position=actual_end,
                distance_into_wall_m=intended - d,
            )

    # 6. Hazard triggers along the path (target_pos → actual_end)
    hazards = compute_hazard_triggers(
        scene=scene,
        combatant_positions_before={combatant_id: target_pos},
        combatant_positions_after={combatant_id: actual_end},
        phase="movement",
    )

    # 7. Fall check — if final position lacks support, resolve_fall.
    fall: FallingResult | None = None
    final_pos = actual_end
    if not is_supported_at(actual_end, scene):
        fall = resolve_fall(
            combatant_id=combatant_id,
            from_pos=actual_end,
            scene=scene,
            gravity_scale=gravity_scale,
        )
        final_pos = fall.landed_at

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
