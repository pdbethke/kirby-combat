"""A wall resists a punch and a blast differently (6E2 p173).

Brick is 5 PD and 10 ED. Until this change the engine held ONE def_value,
so Gorgon's fist and Cheshire's Energy Blast met the same number.
"""
from kirby_combat.scene.scene import Position, Wall
from kirby_combat.scene.construct import construct_from_wall


def _wall(**kw) -> Wall:
    base = dict(
        id="w1", name="brick wall",
        segment=(Position(x=0.0, y=0.0, z=0.0), Position(x=5.0, y=0.0, z=0.0)),
        height_m=4.0,
    )
    base.update(kw)
    return Wall(**base)


def test_a_wall_carries_pd_and_ed_separately():
    w = _wall(def_value=5, ed_value=10, body=3)
    assert (w.pd, w.ed) == (5, 10)


def test_ed_falls_back_to_def_value_when_unset():
    """Every wall built before this change, in this repo and in kirby-api,
    passes only def_value. Those must keep behaving exactly as they did --
    one number for both -- rather than silently becoming ED 0."""
    w = _wall(def_value=6, body=5)
    assert (w.pd, w.ed) == (6, 6)


def test_walls_are_resistant_unless_told_otherwise():
    assert _wall(def_value=5, body=3).resistant is True
    assert _wall(def_value=1, body=1, resistant=False).resistant is False


def test_projection_into_a_construct_carries_all_three():
    """construct_from_wall is how an authored wall reaches combat. If it
    drops the new fields the split is invisible where it matters."""
    c = construct_from_wall(_wall(def_value=5, ed_value=10, body=3, resistant=False))
    assert (c.pd, c.ed, c.resistant) == (5, 10, False)


def test_a_projected_construct_without_ed_also_falls_back():
    c = construct_from_wall(_wall(def_value=6, body=5))
    assert (c.pd, c.ed) == (6, 6)
