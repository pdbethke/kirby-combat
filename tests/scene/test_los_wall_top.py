"""LoS at exactly the wall top (supported-vantages spec §2)."""
from kirby_combat.scene.scene import Position, Wall
from kirby_combat.scene.geometry import line_of_sight_clear

# URBAN_ROOFTOP's stone_wall, verbatim.
WALL = Wall(
    id="stone", name="stone_wall",
    segment=(Position(-16.0, -5.0, 0.0), Position(-2.0, -5.0, 0.0)),
    height_m=8.0,
)
GROUND_TARGET = Position(-10.0, -15.0, 0.0)


def test_standing_on_the_wall_top_sees_over_it():
    """Slightly off the wall's centre-line so the xy segment genuinely
    crosses it — a start point exactly ON the wall line is a degenerate
    intersection and would pass for the wrong reason."""
    on_top = Position(-9.0, -4.8, 8.0)
    assert line_of_sight_clear(on_top, GROUND_TARGET, [WALL]) is True


def test_just_below_the_wall_top_is_still_blocked():
    assert line_of_sight_clear(Position(-9.0, -4.8, 7.9), GROUND_TARGET, [WALL]) is False


def test_rooftop_below_the_wall_top_is_still_blocked():
    """REGRESSION PIN: URBAN_ROOFTOP's 8 m wall deliberately exceeds its
    6 m rooftop so it screens ground<->rooftop lines of fire. 6 < 8 must
    keep blocking."""
    rooftop = Position(0.0, 13.0, 6.0)
    assert line_of_sight_clear(rooftop, GROUND_TARGET, [WALL]) is False
