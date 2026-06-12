"""movement_reach: per-mode traversal legality + landing + fall (movement spec §2)."""
import pytest

from kirby_combat.scene import (
    Scene, SceneBounds, Surface, Wall, Position, AmbientConditions,
)
from kirby_combat.scene.movement_legality import movement_reach, MovementOutcome


# Scene layout:
#   ground surface z=0 over the whole 0..20 x 0..20 floor
#   rooftop surface z=6 over x in [10,20], y in [0,20]
#   wall at x=8 (base z=0, height 8 -> top z=8) spanning the full y, between
#   the ground start (x=2) and the rooftop region (x>=10).
def _arena() -> Scene:
    return Scene(
        id="arena", name="Urban Rooftop",
        bounds=SceneBounds(0, 0, 0, 20, 20, 20),
        surfaces=[
            Surface(id="ground", name="Ground",
                    polygon_xy=[(0, 0), (20, 0), (20, 20), (0, 20)],
                    elevation_m=0.0, surface_type="ground",
                    cover_level=0, is_supporting=True),
            Surface(id="roof", name="Roof",
                    polygon_xy=[(10, 0), (20, 0), (20, 20), (10, 20)],
                    elevation_m=6.0, surface_type="rooftop",
                    cover_level=0, is_supporting=True),
        ],
        walls=[
            Wall(id="w1", name="Wall",
                 segment=(Position(8, 0, 0), Position(8, 20, 0)),
                 height_m=8.0, blocks_los=True, blocks_movement=True),
        ],
        hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )


A_GROUND = Position(2, 10, 0)               # ground, before the wall
B_GROUND_ACROSS_WALL = Position(15, 10, 0)  # ground, beyond the wall (same z)
ROOF_POINT_z6 = Position(15, 10, 6)         # on the rooftop surface, z == elevation
BEYOND_ROOF_EDGE = Position(5, 10, 6)       # z=6 but off the roof polygon -> unsupported
MIDAIR_z6 = Position(5, 10, 6)              # z=6 over ground -> not supported
# NOTE: BEYOND_ROOF_EDGE and MIDAIR_z6 are intentionally the same point — they
# describe the same unsupported coordinate but are named for the test's perspective
# (leap-off-ledge vs. teleport-to-midair).


def test_running_blocked_by_wall():
    scene = _arena()
    out = movement_reach("running", A_GROUND, B_GROUND_ACROSS_WALL,
                         distance_m=12, scene=scene)
    # stopped at/short of the wall — never reaches the across-wall target
    assert out.reachable is False
    assert out.landing != B_GROUND_ACROSS_WALL
    # landing is at/before the wall (x <= 8)
    assert out.landing.x <= 8.0 + 1e-6


def test_leap_clears_wall_and_reaches_rooftop():
    scene = _arena()
    out = movement_reach("leaping", A_GROUND, ROOF_POINT_z6,
                         distance_m=20, scene=scene)
    assert out.reachable is True
    assert out.landing.z == 6.0
    assert out.fall is None


def test_leap_overshoot_off_ledge_falls():
    scene = _arena()
    out = movement_reach("leaping", ROOF_POINT_z6, BEYOND_ROOF_EDGE,
                         distance_m=20, scene=scene)
    assert out.fall is not None
    assert out.fall.fall_distance_m > 0


def test_teleport_to_unsupported_point_not_reachable():
    scene = _arena()
    out = movement_reach("teleportation", A_GROUND, MIDAIR_z6,
                         distance_m=30, scene=scene)
    assert out.reachable is False


def test_teleport_to_rooftop_ok():
    scene = _arena()
    out = movement_reach("teleportation", A_GROUND, ROOF_POINT_z6,
                         distance_m=30, scene=scene)
    assert out.reachable is True
    assert out.landing.z == 6.0


def test_flight_reaches_elevation_in_range():
    scene = _arena()
    out = movement_reach("flight", A_GROUND, ROOF_POINT_z6,
                         distance_m=20, scene=scene)
    assert out.reachable is True
    assert out.fall is None


def test_flight_blocked_by_ceiling():
    scene = _arena()
    above_ceiling = Position(15, 10, 21)   # bounds.max_z is 20
    out = movement_reach("flight", A_GROUND, above_ceiling,
                         distance_m=50, scene=scene)
    assert out.reachable is False


def test_running_off_ledge_falls():
    # Run on the rooftop and step off its edge (x < 10) at z=6 -> unsupported -> fall.
    scene = _arena()
    start = Position(12, 10, 6)
    off_edge = Position(8.5, 10, 6)         # x<10: off the roof, before the wall
    out = movement_reach("running", start, off_edge, distance_m=12, scene=scene)
    assert out.fall is not None
    assert out.fall.fall_distance_m > 0


def test_running_different_elevation_unreachable():
    scene = _arena()
    out = movement_reach("running", A_GROUND, ROOF_POINT_z6,
                         distance_m=30, scene=scene)
    assert out.reachable is False


def test_swimming_only_in_water():
    scene = _arena()
    out = movement_reach("swimming", A_GROUND, B_GROUND_ACROSS_WALL,
                         distance_m=30, scene=scene)
    assert out.reachable is False


def test_swimming_in_water_surface():
    scene = Scene(
        id="pool", name="Pool",
        bounds=SceneBounds(0, 0, -5, 20, 20, 20),
        surfaces=[
            Surface(id="water", name="Water",
                    polygon_xy=[(0, 0), (20, 0), (20, 20), (0, 20)],
                    elevation_m=0.0, surface_type="water",
                    cover_level=0, is_supporting=False),
        ],
        walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    a = Position(2, 2, 0)
    b = Position(10, 10, 0)
    out = movement_reach("swimming", a, b, distance_m=30, scene=scene)
    assert out.reachable is True
    assert out.landing == b


def test_tunneling_ground_gate():
    scene = _arena()
    out = movement_reach("tunneling", A_GROUND, B_GROUND_ACROSS_WALL,
                         distance_m=30, scene=scene)
    assert out.reachable is True


def test_unknown_mode():
    scene = _arena()
    out = movement_reach("teyhwopdjf", A_GROUND, B_GROUND_ACROSS_WALL,
                         distance_m=30, scene=scene)
    assert isinstance(out, MovementOutcome)
    assert out.reachable is False
    assert out.landing == A_GROUND


# ---------------------------------------------------------------------------
# M5 coverage: uncovered branches
# ---------------------------------------------------------------------------

def test_running_wall_beyond_reach_clamps_short():
    """Wall exists on the path but is farther than distance_m.

    The runner stops at the run limit (distance_m from start), not at the
    wall.  reachable is False (target is beyond the wall, regardless).
    """
    scene = _arena()
    # A_GROUND is (2,10,0); wall is at x=8 (6m away); target is at x=15.
    # With distance_m=4 the runner can only cover 4m — stopping at x=6, short
    # of the wall at x=8.  The wall is beyond the reach limit.
    out = movement_reach("running", A_GROUND, B_GROUND_ACROSS_WALL,
                         distance_m=4, scene=scene)
    assert out.reachable is False
    # Clamped to 4m from start (x=2) → landing at x≈6 (the wall is at x=8,
    # so we never hit it this phase).
    assert out.landing.x == pytest.approx(6.0, abs=1e-6)


def test_leap_wall_too_tall_blocks():
    """A wall whose top exceeds the vertical cap is not cleared by the leap.

    Arena wall: base z=0, height=8m → top z=8.  Leaping from z=0 with
    distance_m=6 → vertical_cap=3m.  Wall top (8m) - from_pos.z (0) = 8 > 3
    → wall_clears=False → reachable=False.
    """
    scene = _arena()
    # A_GROUND→ROOF_POINT_z6 crosses the wall at x=8.
    # With distance_m=6: vertical_cap=3 but wall needs 8m clearance.
    out = movement_reach("leaping", A_GROUND, ROOF_POINT_z6,
                         distance_m=6, scene=scene)
    assert out.reachable is False


def test_flight_ceiling_clamp():
    """Flight to a point above bounds.max_z is not reachable; landing is
    clamped to the ceiling (max_z=20 in the arena)."""
    scene = _arena()
    above_ceiling = Position(5, 10, 25)    # above bounds.max_z=20
    out = movement_reach("flight", A_GROUND, above_ceiling,
                         distance_m=50, scene=scene)
    assert out.reachable is False
    # The clamped landing must not exceed the scene ceiling.
    assert out.landing.z <= scene.bounds.max_z + 1e-6


def test_tunneling_different_elevation_not_reachable():
    """Tunneling to a point at a different z is not reachable (v1 same-elevation gate)."""
    scene = _arena()
    # ROOF_POINT_z6 is at z=6; A_GROUND is at z=0 — different elevations.
    out = movement_reach("tunneling", A_GROUND, ROOF_POINT_z6,
                         distance_m=30, scene=scene)
    assert out.reachable is False


def test_movement_reach_combatant_id_threads_to_fall():
    """combatant_id is passed through to FallingResult.combatant_id."""
    scene = _arena()
    # Run on the rooftop and step off — this triggers a fall.
    start = Position(12, 10, 6)
    off_edge = Position(8.5, 10, 6)
    out = movement_reach("running", start, off_edge, distance_m=12,
                         scene=scene, combatant_id="hero_1")
    assert out.fall is not None
    assert out.fall.combatant_id == "hero_1"
