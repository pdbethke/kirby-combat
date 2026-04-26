"""3D geometry utilities for scene queries."""
import pytest
from math import pi, sqrt

from kirby_combat.scene import Position, Wall
from kirby_combat.scene.geometry import (
    distance_3d,
    point_in_polygon_xy,
    segments_intersect_xy,
    line_of_sight_clear,
    angle_between_xy,
)


def test_distance_3d_basic():
    a = Position(0, 0, 0)
    b = Position(3, 4, 0)
    assert distance_3d(a, b) == pytest.approx(5.0)


def test_distance_3d_with_elevation():
    a = Position(0, 0, 0)
    b = Position(0, 0, 4)
    assert distance_3d(a, b) == pytest.approx(4.0)


def test_distance_3d_full_3d():
    a = Position(1, 2, 3)
    b = Position(4, 6, 15)
    # dx=3 dy=4 dz=12 => sqrt(9+16+144) = sqrt(169) = 13
    assert distance_3d(a, b) == pytest.approx(13.0)


def test_point_in_polygon_square():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon_xy((5, 5), square) is True
    assert point_in_polygon_xy((15, 5), square) is False
    assert point_in_polygon_xy((-1, 5), square) is False


def test_point_in_polygon_on_edge_treated_as_inside():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon_xy((0, 5), square) is True    # left edge


def test_segments_cross_returns_true():
    # Horizontal vs vertical crossing at (5,5)
    a1, a2 = (0, 5), (10, 5)
    b1, b2 = (5, 0), (5, 10)
    assert segments_intersect_xy(a1, a2, b1, b2) is True


def test_segments_parallel_no_intersection():
    a1, a2 = (0, 0), (10, 0)
    b1, b2 = (0, 1), (10, 1)
    assert segments_intersect_xy(a1, a2, b1, b2) is False


def test_los_clear_no_walls():
    from_ = Position(0, 0, 1.5)
    to = Position(10, 0, 1.5)
    assert line_of_sight_clear(from_, to, walls=[]) is True


def test_los_blocked_by_wall_between():
    from_ = Position(0, 5, 1.5)
    to = Position(10, 5, 1.5)
    blocker = Wall(
        id="w", name="w",
        segment=(Position(5, 0, 0), Position(5, 10, 0)),
        height_m=3.0, blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )
    assert line_of_sight_clear(from_, to, walls=[blocker]) is False


def test_los_not_blocked_by_short_wall_when_shooter_is_above():
    # Wall is 1m tall; shooter is at 5m elevation; target at 5m
    from_ = Position(0, 5, 5.0)
    to = Position(10, 5, 5.0)
    short_wall = Wall(
        id="w", name="w",
        segment=(Position(5, 0, 0), Position(5, 10, 0)),
        height_m=1.0, blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )
    assert line_of_sight_clear(from_, to, walls=[short_wall]) is True


def test_angle_east_is_zero():
    a = Position(0, 0, 0)
    b = Position(5, 0, 0)
    assert angle_between_xy(a, b) == pytest.approx(0.0)


def test_angle_north_is_half_pi():
    a = Position(0, 0, 0)
    b = Position(0, 5, 0)
    assert angle_between_xy(a, b) == pytest.approx(pi / 2)
