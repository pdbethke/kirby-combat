"""Unit tests for analytic visibility geometry (LoS-aware repositioning §1)."""
from __future__ import annotations

from kirby_combat.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Wall,
)
from kirby_combat.scene.geometry import line_of_sight_clear
from kirby_combat.scene.visibility import (
    _dist, _nearest_point_on_segment, nearest_hidden_point, nearest_visible_point,
)


def test_nearest_point_on_segment_is_the_movement_legality_helper():
    """whole-branch review MINOR 4: movement_legality._nearest_point_on_segment_xy
    is the single surviving definition of this projection (a later task
    imports it from movement_legality by that exact name). visibility must
    reuse it rather than keep a byte-for-byte duplicate that can drift."""
    from kirby_combat.scene.movement_legality import _nearest_point_on_segment_xy

    assert _nearest_point_on_segment is _nearest_point_on_segment_xy


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


# --- nearest_hidden_point (defensive / break-contact) -----------------------


def test_returns_observer_when_already_hidden():
    # Wall between observer and threat -> obs already hidden -> returns obs.
    obs, threat = Position(0, 0, 1.5), Position(20, 0, 1.5)
    wall = _wall(x=10, y0=-5, y1=5, h=8.0)
    p = nearest_hidden_point(obs, threat, _scene(walls=[wall]), radius=10.0)
    assert p == obs


def test_no_cover_returns_farthest_point_to_open_range():
    # No walls -> can't hide -> open range: move ~away, near the radius edge.
    obs, threat = Position(0, 0, 1.5), Position(5, 0, 1.5)
    p = nearest_hidden_point(obs, threat, _scene(walls=[]), radius=12.0)
    assert p is not None
    # opened range -- moved roughly away from the threat, near the radius edge
    assert _dist(obs, p) >= 8.0
    assert _dist(p, threat) > _dist(obs, threat)


def test_behind_cover_point_returned_when_one_exists():
    # Threat has LoS to observer in the open, but a wall just off to the side
    # casts a shadow a short hop away -> a behind-cover point is returned.
    obs, threat = Position(0, 0, 1.5), Position(0, -20, 1.5)
    # Wall running east-west, off to the observer's +x side, between the
    # observer's flank and the threat's sightline to that flank.
    wall = Wall(
        id="w", name="Brick",
        segment=(Position(2, -4, 0.0), Position(8, -4, 0.0)),
        height_m=8.0, blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )
    p = nearest_hidden_point(obs, threat, _scene(walls=[wall]), radius=12.0)
    assert p is not None
    # The returned point is behind cover: threat has NO LoS to it.
    assert line_of_sight_clear(threat, p, [wall]) is False


def test_multi_wall_returns_only_a_point_clear_of_all_walls():
    # Wall A blocks the direct line; a naive flank past A's near end is then
    # blocked by Wall B. nearest_visible_point must return a point clear of BOTH
    # (the full-occluder-set verification), not just clear of A.
    from kirby_combat.scene.geometry import line_of_sight_clear
    obs, tgt = Position(0, 0, 1.5), Position(20, 0, 1.5)
    wall_a = _wall(x=10, y0=-3, y1=3, h=8.0, wid="A")
    wall_b = _wall(x=15, y0=2, y1=12, h=8.0, wid="B")   # blocks the +y flank
    scene = _scene(walls=[wall_a, wall_b])
    p = nearest_visible_point(obs, tgt, scene, radius=40.0, vertical_reach=0.0)
    assert p is not None
    # whatever point it returns, it must have LoS clear of BOTH walls:
    assert line_of_sight_clear(p, tgt, [wall_a, wall_b]) is True
