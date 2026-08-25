"""kirby-cost derives the dice; this package acts on them.

These are not tests of the arithmetic -- kirby-cost's own oracle suite does
that against Hero Designer. They are tests that this package does not have a
SECOND copy of the arithmetic.

It did. "5 STR to the die" existed three times across two repositories: in
kirby-cost's `Strength.damage_dice`, in `str_strike_view`, and in
`_str_augment_dice`. They agreed, and nothing was keeping them that way. The
next person to touch one would not have known the others existed, and both
answers would have looked plausible.
"""
import pytest

from kirby_cost.engine.damage import augment_with_str, strike_dice
from kirby_combat.hero_view import _str_augment_dice


@pytest.mark.parametrize("strength", range(0, 61))
def test_a_bare_strike_reports_the_engine_dice(strength):
    """The half-die is the part a re-derivation loses: STR 13 is 2 1/2d6,
    and `STR // 5` alone would say 2d6."""
    assert strike_dice(strength) == (strength // 5, (strength % 5) >= 3)


def test_the_half_die_is_actually_exercised():
    """Guards the guard. A range that never produced a half-die would make
    every assertion above pass for the wrong reason."""
    halves = [s for s in range(0, 61) if strike_dice(s)[1]]
    assert len(halves) == 24, f"expected 24 STR values to buy a half-die, got {len(halves)}"


@pytest.mark.parametrize("damage_type", ["normal", "killing"])
def test_str_augmentation_is_the_engine_s(damage_type):
    """Every combination, not a sample: the wrapper must add nothing."""
    for full_dice in range(0, 9):
        for half_die in (False, True):
            for strength in range(0, 61):
                assert _str_augment_dice(full_dice, half_die, damage_type, strength) == \
                    augment_with_str(full_dice, half_die, damage_type, strength)


def test_kirby_cost_is_a_hard_dependency():
    """It is imported at module scope above. If it were still optional this
    file would not collect -- which is the point: there is no configuration
    in which this package runs without the engine that owns its numbers."""
    import kirby_cost
    assert kirby_cost.__file__
