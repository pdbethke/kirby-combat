"""Unit tests for analytic visibility geometry (LoS-aware repositioning §1)."""
from __future__ import annotations

from kirby_combat.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Wall,
)
from kirby_combat.scene.geometry import line_of_sight_clear
from kirby_combat.scene.visibility import nearest_visible_point


def _scene(walls=None) -> Scene:
    return Scene(
        id="s1", name="Test",
        bounds=SceneBounds(-200, -200, -50, 200, 200, 50),
        surfaces=[],
        walls=list(walls or []),
        hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )


def _wall(x, y0, y1, base_z=0.0, h=8.0, wid="w"):
    return Wall(
        id=wid, name="Brick",
        segment=(Position(x, y0, base_z), Position(x, y1, base_z)),
        height_m=h, blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )


def test_returns_observer_when_already_visible():
    # No wall -> already clear -> returns the observer point (no move needed).
    obs, tgt = Position(0, 0, 1.5), Position(10, 0, 1.5)
    p = nearest_visible_point(obs, tgt, _scene(walls=[]), radius=20.0)
    assert p == obs


def test_over_the_top_when_vertical_reach_clears_the_wall():
    # 8m wall between; a flyer/teleporter with vertical_reach can rise over it.
    obs, tgt = Position(0, 0, 1.5), Position(20, 0, 1.5)
    wall = _wall(x=10, y0=-5, y1=5, h=8.0)
    p = nearest_visible_point(obs, tgt, _scene(walls=[wall]),
                              radius=30.0, vertical_reach=10.0)
    assert p is not None
    assert p.z > 8.0                      # rose above the wall top
    # and it actually has LoS to the target:
    assert line_of_sight_clear(p, tgt, [wall]) is True


def test_flank_the_wall_end_on_the_ground():
    # Finite wall; no vertical reach (runner) -> a point past the wall's end clears it.
    obs, tgt = Position(0, 0, 1.5), Position(20, 0, 1.5)
    wall = _wall(x=10, y0=-3, y1=3, h=8.0)   # ends at y=+/-3
    p = nearest_visible_point(obs, tgt, _scene(walls=[wall]),
                              radius=30.0, vertical_reach=0.0)
    assert p is not None
    assert line_of_sight_clear(p, tgt, [wall]) is True
    assert abs(p.z - 1.5) < 0.01           # stayed on the ground (no vertical)


def test_none_when_no_clear_point_within_radius():
    # A long wall with no reachable gap within a tiny radius -> None.
    obs, tgt = Position(0, 0, 1.5), Position(20, 0, 1.5)
    wall = _wall(x=10, y0=-100, y1=100, h=8.0)
    p = nearest_visible_point(obs, tgt, _scene(walls=[wall]),
                              radius=2.0, vertical_reach=0.0)
    assert p is None
