"""3D geometry utilities for scene queries."""
from __future__ import annotations

from math import atan2, sqrt
from typing import Iterable

from kirby_combat.scene.scene import Position, Wall


def distance_3d(a: Position, b: Position) -> float:
    """Euclidean 3D distance in meters."""
    dx = b.x - a.x
    dy = b.y - a.y
    dz = b.z - a.z
    return sqrt(dx * dx + dy * dy + dz * dz)


def angle_between_xy(a: Position, b: Position) -> float:
    """Angle (radians) from a to b in the xy-plane. 0 = +x (east), pi/2 = +y (north)."""
    return atan2(b.y - a.y, b.x - a.x)


def point_in_polygon_xy(point: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test in xy. Edges count as inside."""
    x, y = point
    n = len(poly)
    inside = False
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        # Edge inclusion: if point lies on the segment, return True
        if _on_segment((x1, y1), (x2, y2), (x, y)):
            return True
        if ((y1 > y) != (y2 > y)):
            x_intersect = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_intersect:
                inside = not inside
    return inside


def _on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    """True if p lies on segment ab (inclusive of endpoints)."""
    cross = (p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])
    if abs(cross) > 1e-9:
        return False
    if min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9 and \
       min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9:
        return True
    return False


def segments_intersect_xy(
    a1: tuple[float, float], a2: tuple[float, float],
    b1: tuple[float, float], b2: tuple[float, float],
) -> bool:
    """True if segments a1a2 and b1b2 intersect in the xy-plane."""
    def ccw(p1, p2, p3):
        return (p3[1] - p1[1]) * (p2[0] - p1[0]) > (p2[1] - p1[1]) * (p3[0] - p1[0])
    return ccw(a1, b1, b2) != ccw(a2, b1, b2) and ccw(a1, a2, b1) != ccw(a1, a2, b2)


def path_crosses_polygon(
    a: tuple[float, float], b: tuple[float, float],
    poly: list[tuple[float, float]],
) -> bool:
    """True if the segment from a to b crosses any edge of the polygon."""
    n = len(poly)
    for i in range(n):
        p1 = poly[i]
        p2 = poly[(i + 1) % n]
        if segments_intersect_xy(a, b, p1, p2):
            return True
    return False


def segment_intersection_xy(
    a1: tuple[float, float], a2: tuple[float, float],
    b1: tuple[float, float], b2: tuple[float, float],
) -> "tuple[float, float] | None":
    """Compute the (x, y) intersection point of segments a1a2 and b1b2, or
    None if they are parallel or do not intersect."""
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


def wall_height_blocks(target_z: float, wall: Wall) -> bool:
    """True if the wall's vertical extent covers target_z.

    wall_base_z = min(segment[0].z, segment[1].z)
    wall_top_z  = wall_base_z + wall.height_m
    Blocks when wall_base_z <= target_z <= wall_top_z.
    """
    base = min(wall.segment[0].z, wall.segment[1].z)
    top = base + wall.height_m
    return base <= target_z <= top


def first_blocking_wall(from_: Position, to: Position, walls: Iterable[Wall]) -> "Wall | None":
    """Return the LoS-blocking wall nearest to `from_` that breaks the from_->to
    line, or None if LoS is clear.

    Blocking predicate (identical to the original line_of_sight_clear):
      - wall.blocks_los is True, AND
      - the wall's segment intersects the from_->to segment in xy, AND
      - max(from_.z, to.z) <= wall_base_z + wall.height_m
        where wall_base_z = min(segment[0].z, segment[1].z).
    Nearest is determined by distance from `from_` to the wall's midpoint.
    """
    blockers: list[Wall] = []
    for w in walls:
        if not w.blocks_los:
            continue
        w_a = (w.segment[0].x, w.segment[0].y)
        w_b = (w.segment[1].x, w.segment[1].y)
        if not segments_intersect_xy((from_.x, from_.y), (to.x, to.y), w_a, w_b):
            continue
        wall_base_z = min(w.segment[0].z, w.segment[1].z)
        wall_top_z = wall_base_z + w.height_m
        shooter_z = max(from_.z, to.z)
        if shooter_z <= wall_top_z:
            blockers.append(w)
    if not blockers:
        return None

    def _d2(w: Wall) -> float:
        mx = (w.segment[0].x + w.segment[1].x) / 2.0
        my = (w.segment[0].y + w.segment[1].y) / 2.0
        return (mx - from_.x) ** 2 + (my - from_.y) ** 2

    return min(blockers, key=_d2)


def line_of_sight_clear(from_: Position, to: Position, walls: Iterable[Wall]) -> bool:
    """True if no LoS-blocking wall intersects the from->to segment in xy
    AND at least one of (from_.z, to.z) lies above the wall's height range.

    Height check: LoS is clear if both endpoints are above the wall's height,
    or if neither endpoint is within the wall's vertical range on its side.
    Simplified height check: if max(from_.z, to.z) > wall.height_m, LoS clears.
    """
    return first_blocking_wall(from_, to, walls) is None
