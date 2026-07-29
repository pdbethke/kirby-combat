"""climb_difficulty: the ordinary/difficult split from 6E1 p70."""
from kirby_combat.scene.scene import Position, Surface, Wall, is_climbable


def _wall(diff=None):
    return Wall(
        id="w", name="stone wall",
        segment=(Position(-16.0, -5.0, 0.0), Position(-2.0, -5.0, 0.0)),
        height_m=8.0, climb_difficulty=diff,
    )


def test_default_is_unclimbable():
    """Every scene already in production must be unchanged."""
    assert _wall().climb_difficulty is None
    assert is_climbable(_wall()) is False


def test_zero_is_ordinary_and_climbable():
    """0 = ordinary (a ladder): climbable, and needs no Skill."""
    assert is_climbable(_wall(0)) is True


def test_positive_is_difficult_and_climbable():
    assert is_climbable(_wall(3)) is True


def test_surface_carries_it_too():
    s = Surface("s", "cliff", [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
                4.0, "rubble", climb_difficulty=2)
    assert is_climbable(s) is True
