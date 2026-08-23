"""Cover resolution tests."""
import pytest

from kirby_combat.scene import (
    Scene, SceneBounds, Surface, Wall, Position, AmbientConditions,
)
from kirby_combat.scene.cover import compute_cover_level, cover_ocv_modifier


def _empty_scene() -> Scene:
    return Scene(
        id="s1", name="Empty",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )


def _scene_with_wall(wall: Wall, *, surfaces: list[Surface] | None = None) -> Scene:
    return Scene(
        id="s1", name="Test",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=list(surfaces or []),
        walls=[wall],
        hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )


def test_no_cover_when_no_walls():
    s = _empty_scene()
    level = compute_cover_level(
        shooter_pos=Position(0, 5, 1.5),
        target_pos=Position(20, 5, 1.5),
        target_is_prone_or_diving=False,
        scene=s,
    )
    assert level == 0


def test_full_cover_when_wall_blocks_los():
    wall = Wall(
        id="w", name="Brick",
        segment=(Position(10, 0, 0), Position(10, 10, 0)),
        height_m=3.0, blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )
    s = _scene_with_wall(wall)
    level = compute_cover_level(
        shooter_pos=Position(0, 5, 1.5),
        target_pos=Position(20, 5, 1.5),
        target_is_prone_or_diving=False,
        scene=s,
    )
    assert level == 4


def test_partial_cover_from_lower_walls():
    wall = Wall(
        id="w", name="Hedge",
        segment=(Position(10, 0, 0), Position(10, 10, 0)),
        height_m=3.0, blocks_los=True, blocks_movement=True,
        cover_level=2, body=2,
    )
    s = _scene_with_wall(wall)
    level = compute_cover_level(
        shooter_pos=Position(0, 5, 1.5),
        target_pos=Position(20, 5, 1.5),
        target_is_prone_or_diving=False,
        scene=s,
    )
    assert level == 2


def test_no_cover_when_wall_does_not_block_los_segment():
    # Wall is parallel to LoS path, doesn't intersect.
    wall = Wall(
        id="w", name="Wall behind shooter",
        segment=(Position(0, 10, 0), Position(20, 10, 0)),
        height_m=3.0, blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )
    s = _scene_with_wall(wall)
    level = compute_cover_level(
        shooter_pos=Position(0, 5, 1.5),
        target_pos=Position(20, 5, 1.5),
        target_is_prone_or_diving=False,
        scene=s,
    )
    assert level == 0


def test_short_wall_does_not_provide_cover_when_shooter_is_above():
    # Shooter at z=5, wall is 1m tall — LoS is clear via the geometry check.
    short_wall = Wall(
        id="w", name="Low wall",
        segment=(Position(10, 0, 0), Position(10, 10, 0)),
        height_m=1.0, blocks_los=True, blocks_movement=True,
        cover_level=4, body=4,
    )
    s = _scene_with_wall(short_wall)
    level = compute_cover_level(
        shooter_pos=Position(0, 5, 5.0),
        target_pos=Position(20, 5, 5.0),
        target_is_prone_or_diving=False,
        scene=s,
    )
    assert level == 0       # wall doesn't block elevated shooter


def test_nearest_wall_to_target_wins_when_multiple_block():
    # Two walls between shooter and target. Wall A is near shooter (cover 2),
    # Wall B is near target (cover 4). Should pick wall B (nearer the target).
    wall_a = Wall(
        id="a", name="A", segment=(Position(5, 0, 0), Position(5, 10, 0)),
        height_m=3.0, blocks_los=True, blocks_movement=True, cover_level=2, body=4,
    )
    wall_b = Wall(
        id="b", name="B", segment=(Position(15, 0, 0), Position(15, 10, 0)),
        height_m=3.0, blocks_los=True, blocks_movement=True, cover_level=4, body=6,
    )
    s = Scene(
        id="s1", name="Two walls",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[], walls=[wall_a, wall_b], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    level = compute_cover_level(
        shooter_pos=Position(0, 5, 1.5),
        target_pos=Position(20, 5, 1.5),
        target_is_prone_or_diving=False,
        scene=s,
    )
    assert level == 4   # nearer-to-target wall wins (cover_level 4)


def test_target_inside_cover_surface_gains_surface_cover():
    foxhole = Surface(
        id="foxhole", name="Foxhole",
        polygon_xy=[(15, 0), (25, 0), (25, 10), (15, 10)],
        elevation_m=0.0, surface_type="rubble",
        cover_level=3, is_supporting=True,
    )
    s = Scene(
        id="s1", name="With foxhole",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[foxhole], walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    level = compute_cover_level(
        shooter_pos=Position(0, 5, 1.5),
        target_pos=Position(20, 5, 0),       # inside foxhole polygon
        target_is_prone_or_diving=False,
        scene=s,
    )
    assert level == 3


def test_max_of_wall_and_surface_cover_when_both_apply():
    foxhole = Surface(
        id="foxhole", name="Foxhole",
        polygon_xy=[(15, 0), (25, 0), (25, 10), (15, 10)],
        elevation_m=0.0, surface_type="rubble",
        cover_level=3, is_supporting=True,
    )
    wall = Wall(
        id="w", name="Wall", segment=(Position(10, 0, 0), Position(10, 10, 0)),
        height_m=3.0, blocks_los=True, blocks_movement=True,
        cover_level=2, body=4,
    )
    s = Scene(
        id="s1", name="Wall+foxhole",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[foxhole], walls=[wall], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    level = compute_cover_level(
        shooter_pos=Position(0, 5, 1.5),
        target_pos=Position(20, 5, 0),
        target_is_prone_or_diving=False,
        scene=s,
    )
    # Wall gives 2 (it blocks LoS), foxhole gives 3 → max is 3
    assert level == 3


def test_prone_or_diving_adds_one_level():
    wall = Wall(
        id="w", name="W", segment=(Position(10, 0, 0), Position(10, 10, 0)),
        height_m=3.0, blocks_los=True, blocks_movement=True,
        cover_level=2, body=4,
    )
    s = _scene_with_wall(wall)
    level = compute_cover_level(
        shooter_pos=Position(0, 5, 1.5),
        target_pos=Position(20, 5, 1.5),
        target_is_prone_or_diving=True,
        scene=s,
    )
    assert level == 3       # 2 + 1


def test_prone_bonus_capped_at_4():
    wall = Wall(
        id="w", name="Brick", segment=(Position(10, 0, 0), Position(10, 10, 0)),
        height_m=3.0, blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )
    s = _scene_with_wall(wall)
    level = compute_cover_level(
        shooter_pos=Position(0, 5, 1.5),
        target_pos=Position(20, 5, 1.5),
        target_is_prone_or_diving=True,
        scene=s,
    )
    assert level == 4    # 4 + 1 capped at 4


def test_prone_alone_no_walls_returns_zero():
    """Being prone on open ground gives no cover unless there's a surface."""
    s = _empty_scene()
    level = compute_cover_level(
        shooter_pos=Position(0, 5, 1.5),
        target_pos=Position(20, 5, 1.5),
        target_is_prone_or_diving=True,
        scene=s,
    )
    # Bonus is +1 but it's added to a 0 base. Whether to apply prone bonus
    # without any base cover is a rule call. RAW says diving for cover GRANTS
    # partial cover; the +1 bonus assumes existing concealment.
    # For this engine: prone bonus only applies when there's ≥ 1 base cover.
    assert level == 0


# ---- cover_ocv_modifier — RAW table per 6E2 p45 -----


def test_cover_ocv_modifier_matches_6e2_p45_table():
    """Per 6E2 p45 §BEHIND COVER MODIFIERS — six discrete percent buckets."""
    # 0-10% bucket: no penalty.
    assert cover_ocv_modifier(0) == 0
    assert cover_ocv_modifier(1) == 0
    assert cover_ocv_modifier(10) == 0
    # 11-24% bucket: -1.
    assert cover_ocv_modifier(11) == -1
    assert cover_ocv_modifier(24) == -1
    # 25-50% bucket: -2.
    assert cover_ocv_modifier(25) == -2
    assert cover_ocv_modifier(50) == -2
    # 51-74% bucket: -3.
    assert cover_ocv_modifier(51) == -3
    assert cover_ocv_modifier(74) == -3
    # 75-90% bucket: -4.
    assert cover_ocv_modifier(75) == -4
    assert cover_ocv_modifier(90) == -4
    # 91-100% bucket: -8 (head-only / full cover).
    assert cover_ocv_modifier(91) == -8
    assert cover_ocv_modifier(100) == -8


def test_cover_ocv_modifier_clamps_out_of_range_inputs():
    """Negative or >100 inputs are clamped to [0, 100]."""
    assert cover_ocv_modifier(-50) == 0
    assert cover_ocv_modifier(150) == -8


# ---- wall-top parity with geometry.first_blocking_wall (supported-vantages) ----
#
# cover._wall_blocks_los is a hand-copy of geometry.first_blocking_wall's
# height predicate (see its docstring). geometry uses strict `<` (standing
# exactly on the wall top sees over it); cover used `<=`. Making wall tops
# standable makes shooter_z == wall_top_z reachable, so the divergence is
# no longer inert: a shooter standing on the wall top must NOT be told the
# wall behind him grants cover.

_ROOFTOP_WALL = Wall(
    id="stone", name="stone_wall",
    segment=(Position(-16.0, -5.0, 0.0), Position(-2.0, -5.0, 0.0)),
    height_m=8.0,
)
_GROUND_TARGET = Position(-10.0, -15.0, 0.0)


def test_shooter_exactly_at_wall_top_gets_no_cover_from_that_wall():
    s = _scene_with_wall(_ROOFTOP_WALL)
    level = compute_cover_level(
        shooter_pos=Position(-9.0, -4.8, 8.0),
        target_pos=_GROUND_TARGET,
        target_is_prone_or_diving=False,
        scene=s,
    )
    assert level == 0


def test_shooter_just_below_the_wall_top_still_gets_cover_from_it():
    s = _scene_with_wall(_ROOFTOP_WALL)
    level = compute_cover_level(
        shooter_pos=Position(-9.0, -4.8, 7.9),
        target_pos=_GROUND_TARGET,
        target_is_prone_or_diving=False,
        scene=s,
    )
    assert level == 4
