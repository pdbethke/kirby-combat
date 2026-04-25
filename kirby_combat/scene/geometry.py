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


def line_of_sight_clear(from_: Position, to: Position, walls: Iterable[Wall]) -> bool:
    """True if no LoS-blocking wall intersects the from->to segment in xy
    AND at least one of (from_.z, to.z) lies above the wall's height range.

    Height check: LoS is clear if both endpoints are above the wall's height,
    or if neither endpoint is within the wall's vertical range on its side.
    Simplified height check: if max(from_.z, to.z) > wall.height_m, LoS clears.
    """
    for w in walls:
        if not w.blocks_los:
            continue
        w_a = (w.segment[0].x, w.segment[0].y)
        w_b = (w.segment[1].x, w.segment[1].y)
        if segments_intersect_xy((from_.x, from_.y), (to.x, to.y), w_a, w_b):
            # Check height: wall starts at segment's z (min_z) and goes up height_m
            wall_base_z = min(w.segment[0].z, w.segment[1].z)
            wall_top_z = wall_base_z + w.height_m
            shooter_z = max(from_.z, to.z)
            if shooter_z <= wall_top_z:
                return False
    return True
