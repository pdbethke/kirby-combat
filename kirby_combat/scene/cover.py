"""Cover resolution.

Two layers:
  1. ``compute_cover_level`` — scene-aware analysis returning a 0-4 abstract
     cover *level* (a property of Walls/Surfaces, not directly the OCV penalty).
  2. ``cover_ocv_modifier(percent_covered)`` — RAW lookup: percent of target
     covered → OCV penalty per 6E2 p45 §BEHIND COVER MODIFIERS.

Per 6E2 p45 §BEHIND COVER MODIFIERS, the OCV penalty has six discrete buckets:
    0-10%   →  0    (no cover / under cover but exposed)
    11-24%  → -1    (light cover, e.g., behind a chair)
    25-50%  → -2    (half cover, e.g., behind a low wall, knee-deep in water)
    51-74%  → -3    (heavy cover, e.g., crouched behind a wall)
    75-90%  → -4    (full cover except head/torso)
    91-100% → -8    (head only / full cover)

Algorithm for ``compute_cover_level`` (scene analysis):
    1. If LoS clear (no walls intersect between shooter and target with sufficient
       height to block), no wall cover applies.
    2. Otherwise, of the walls that block LoS, pick the one whose midpoint is
       closest to the target — that's the wall providing cover.
    3. Surface cover: if target's (x, y) is inside a surface polygon and that
       surface has cover_level > 0, take max(wall_cover, surface_cover).
    4. If target_is_prone_or_diving, add +1 (capped at 4) — but ONLY if the
       base cover is already > 0 (RAW: prone alone in open ground = no cover).
"""
from __future__ import annotations

from kirby_combat.scene.scene import Position, Scene, Wall, Surface
from kirby_combat.scene.geometry import (
    distance_3d, point_in_polygon_xy, segments_intersect_xy,
)


# Per 6E2 p45 §BEHIND COVER MODIFIERS — discrete percent-of-target-covered
# buckets map to OCV penalties. Each tuple is (max_percent_in_bucket, ocv_mod).
_COVER_PERCENT_TO_OCV: list[tuple[int, int]] = [
    (10, 0),      # 0-10%: no penalty
    (24, -1),     # 11-24%: light cover
    (50, -2),     # 25-50%: half cover
    (74, -3),     # 51-74%: heavy cover
    (90, -4),     # 75-90%: full cover except head/torso
    (100, -8),    # 91-100%: head only / full cover
]


def cover_ocv_modifier(percent_covered: int) -> int:
    """Return the OCV penalty for an attack on a target this percent covered.

    Per 6E2 p45 §BEHIND COVER MODIFIERS. Input is clamped to [0, 100].
    """
    pct = max(0, min(100, int(percent_covered)))
    for max_pct, mod in _COVER_PERCENT_TO_OCV:
        if pct <= max_pct:
            return mod
    return -8  # safety fallback (unreachable after clamp)


def _wall_blocks_los(shooter: Position, target: Position, wall: Wall) -> bool:
    """True if this single wall blocks the LoS between shooter and target.

    Mirrors the height-aware logic in geometry.line_of_sight_clear, but for one
    specific wall — needed because we want to identify WHICH wall is providing
    cover, not just whether ANY wall does.
    """
    if not wall.blocks_los:
        return False
    w_a = (wall.segment[0].x, wall.segment[0].y)
    w_b = (wall.segment[1].x, wall.segment[1].y)
    if not segments_intersect_xy(
        (shooter.x, shooter.y), (target.x, target.y), w_a, w_b
    ):
        return False
    wall_base_z = min(wall.segment[0].z, wall.segment[1].z)
    wall_top_z = wall_base_z + wall.height_m
    shooter_z = max(shooter.z, target.z)
    return shooter_z <= wall_top_z


def _wall_midpoint(wall: Wall) -> Position:
    a, b = wall.segment
    return Position(
        x=(a.x + b.x) / 2.0,
        y=(a.y + b.y) / 2.0,
        z=(a.z + b.z) / 2.0,
    )


def _surface_cover_for(target: Position, surfaces: list[Surface]) -> int:
    """Return the max cover_level of any surface containing the target's xy.

    Surfaces matter for cover only when they have cover_level > 0
    (foxholes, rubble, etc.). Standard ground surfaces have cover_level=0.
    """
    best = 0
    for surf in surfaces:
        if surf.cover_level <= 0:
            continue
        if point_in_polygon_xy((target.x, target.y), surf.polygon_xy):
            best = max(best, surf.cover_level)
    return best


def compute_cover_level(
    *,
    shooter_pos: Position,
    target_pos: Position,
    target_is_prone_or_diving: bool,
    scene: Scene,
) -> int:
    """Return cover level 0-4 the target enjoys against the shooter.

    Caller converts to OCV penalty per the 6E table.
    """
    # 1. Find blocking walls; pick the one nearest the target.
    blocking = [w for w in scene.walls if _wall_blocks_los(shooter_pos, target_pos, w)]
    wall_cover = 0
    if blocking:
        nearest = min(blocking, key=lambda w: distance_3d(_wall_midpoint(w), target_pos))
        wall_cover = nearest.cover_level

    # 2. Surface cover (foxhole etc).
    surface_cover = _surface_cover_for(target_pos, scene.surfaces)

    base_cover = max(wall_cover, surface_cover)

    # 3. Prone / diving bonus — only when there's existing cover.
    if target_is_prone_or_diving and base_cover > 0:
        return min(4, base_cover + 1)
    return base_cover
