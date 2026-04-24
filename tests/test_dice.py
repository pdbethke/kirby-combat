"""Dice roller protocol tests."""
from kirby_combat.dice import DiceRoller, RandomRoller, FakeRoller


def test_random_roller_in_range():
    r = RandomRoller(seed=42)
    for _ in range(100):
        result = r.roll_dice(3, sides=6)
        assert len(result) == 3
        assert all(1 <= d <= 6 for d in result)


def test_random_roller_reproducible_with_seed():
    a = RandomRoller(seed=12345)
    b = RandomRoller(seed=12345)
    for _ in range(10):
        assert a.roll_dice(3, sides=6) == b.roll_dice(3, sides=6)


def test_fake_roller_returns_sequence():
    f = FakeRoller([[3, 4, 5], [1, 2, 3]])
    assert f.roll_dice(3, sides=6) == [3, 4, 5]
    assert f.roll_dice(3, sides=6) == [1, 2, 3]


def test_fake_roller_raises_when_exhausted():
    import pytest
    f = FakeRoller([[3, 4, 5]])
    f.roll_dice(3, sides=6)
    with pytest.raises(IndexError):
        f.roll_dice(3, sides=6)


def test_fake_roller_half_die():
    f = FakeRoller([[3, 4, 5]], half_die_results=[2])
    assert f.roll_dice(3, sides=6) == [3, 4, 5]
    assert f.roll_half_die() == 2
