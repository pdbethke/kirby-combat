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


def test_fake_roller_rejects_a_fixture_of_the_wrong_size():
    """A fixture that does not match the call is a test authoring mistake,
    and a silent mismatch would feed the resolver the wrong dice."""
    import pytest
    f = FakeRoller([[3, 4, 5]])
    with pytest.raises(ValueError, match="asked for 2 dice"):
        f.roll_dice(2, sides=6)


def test_fake_roller_isolates_inputs():
    # After constructing FakeRoller, mutating the passed-in lists should not
    # affect what FakeRoller yields.
    dice_in = [[3, 4, 5], [1, 2, 3]]
    f = FakeRoller(dice_in)
    dice_in[0][0] = 99
    dice_in[1] = [9, 9, 9]
    assert f.roll_dice(3, sides=6) == [3, 4, 5]
    assert f.roll_dice(3, sides=6) == [1, 2, 3]


def test_random_roller_accepts_whole_valued_float_count():
    """Canon HDC imports compute dice counts from float stats — the
    cost engine's characteristic_value() returns float, so e.g.
    PRE 60.0 // 5 = 12.0 dice. Whole-valued float counts must roll."""
    r = RandomRoller(seed=7)
    result = r.roll_dice(12.0)
    assert len(result) == 12
    assert all(1 <= d <= 6 for d in result)


def test_random_roller_rejects_fractional_count():
    """A fractional count means a half-die leaked into the d6 count.
    A half die is an extra whole d6 that resolution.damage converts;
    reject rather than silently truncate (truncation drops the half die)."""
    import pytest
    r = RandomRoller(seed=7)
    with pytest.raises(ValueError, match="whole number"):
        r.roll_dice(4.5)
