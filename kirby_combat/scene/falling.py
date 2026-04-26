"""Falling — support check, falling damage, landing resolution.

Note: Dorman's reference implementation does not include falling damage
computation. The 1d6/2m + 20d6 cap formula is our interpretation per HERO 6E2;
RAW-verify the exact cap and per-meter rate against the rulebook before
relying on this in production.
"""
from __future__ import annotations

from dataclasses import dataclass

from kirby_combat.scene.scene import Position, Scene, Surface
from kirby_combat.scene.geometry import point_in_polygon_xy


@dataclass(frozen=True)
class FallingResult:
    combatant_id: str
    from_pos: Position
    landed_at: Position
    fall_distance_m: float
    damage_dice: int         # normal damage dice, vs PD


def is_supported_at(pos: Position, scene: Scene) -> bool:
    """True if any supporting surface exists at pos.z within the combatant's xy-footprint.

    Simplified: a combatant's footprint is just its xy point. A surface supports
    iff point_in_polygon_xy(pos.xy, surface.polygon_xy) AND surface.elevation_m == pos.z
    AND surface.is_supporting.
    """
    for surf in scene.surfaces:
        if not surf.is_supporting:
            continue
        if abs(surf.elevation_m - pos.z) > 1e-6:
            continue
        if point_in_polygon_xy((pos.x, pos.y), surf.polygon_xy):
            return True
    return False


def compute_falling_damage(fall_distance_m: float) -> int:
    """per HERO 6E2: 1d6 normal damage per 2m fallen, cap 20d6 (terminal velocity)."""
    if fall_distance_m < 2:
        return 0
    dice = int(fall_distance_m // 2)
    return min(dice, 20)


def _highest_supporting_surface_below(pos: Position, scene: Scene) -> Surface | None:
    """Return the supporting surface with the highest elevation that:
    - is below pos.z
    - contains pos.xy in its polygon
    - is_supporting is True
    """
    candidates = [
        s for s in scene.surfaces
        if s.is_supporting
        and s.elevation_m < pos.z
        and point_in_polygon_xy((pos.x, pos.y), s.polygon_xy)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.elevation_m)


def resolve_fall(
    combatant_id: str,
    from_pos: Position,
    scene: Scene,
    gravity_scale: float = 1.0,
) -> FallingResult:
    """Resolve a fall from `from_pos`. Finds the highest supporting surface
    directly below in the xy footprint; landed_at.z = that surface's elevation.
    If no supporting surface below, lands at bounds.min_z (ground level).

    `gravity_scale` multiplies the effective fall distance for damage purposes
    (1.0 = Earth-normal). Lower gravity -> less damage; higher -> more.
    """
    landing_surface = _highest_supporting_surface_below(from_pos, scene)
    if landing_surface is not None:
        landed_z = landing_surface.elevation_m
    else:
        landed_z = scene.bounds.min_z
    landed_at = Position(x=from_pos.x, y=from_pos.y, z=landed_z, facing=from_pos.facing)
    fall_distance = (from_pos.z - landed_z) * gravity_scale
    damage = compute_falling_damage(fall_distance)
    return FallingResult(
        combatant_id=combatant_id,
        from_pos=from_pos,
        landed_at=landed_at,
        fall_distance_m=fall_distance,
        damage_dice=damage,
    )
