"""The roller is fair, and every roll it makes can be replayed.

Trust is the product here. A combat engine can assert that its dice were
fair; a module that ships its RNG, its fairness tests and its seed can prove
it. These are the tests that make the claim checkable.

Every test is SEEDED and therefore deterministic -- a fairness test that
fails once a fortnight teaches people to re-run CI, which is worse than not
having it. The seeds below are arbitrary but fixed; the critical values are
standard.
"""
from __future__ import annotations

import math

import pytest

from kirby_combat.dice import RandomRoller

#: Chi-square critical values, 5 degrees of freedom (a d6 has six outcomes).
#: At p=0.001 a fair die exceeds this once in a thousand runs; the seeds are
#: fixed, so for THESE runs it either passes forever or fails forever.
CHI2_DF5_P001 = 20.515

#: 35 degrees of freedom, for the 36 ordered pairs in the independence test.
CHI2_DF35_P001 = 66.619


def _counts(values, faces=6):
    counts = [0] * faces
    for v in values:
        counts[v - 1] += 1
    return counts


def _chi_square(counts):
    """Pearson's chi-square against a uniform expectation."""
    n = sum(counts)
    expected = n / len(counts)
    return sum((c - expected) ** 2 / expected for c in counts)


# ---------------------------------------------------------------------------
# The shape of what comes back
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("count", [0, 1, 3, 12, 60])
def test_it_returns_exactly_the_dice_asked_for(count):
    assert len(RandomRoller(seed=1).roll_dice(count)) == count


@pytest.mark.parametrize("sides", [2, 3, 6, 20])
def test_every_die_lands_in_range(sides):
    rolls = RandomRoller(seed=2).roll_dice(2000, sides=sides)
    assert min(rolls) >= 1
    assert max(rolls) <= sides


def test_every_face_of_a_d6_actually_appears():
    """Guards the guard: a roller stuck on one face would pass a range test."""
    assert set(RandomRoller(seed=3).roll_dice(500)) == {1, 2, 3, 4, 5, 6}


# ---------------------------------------------------------------------------
# Fairness
# ---------------------------------------------------------------------------

def test_a_d6_is_uniform_over_sixty_thousand_rolls():
    counts = _counts(RandomRoller(seed=4).roll_dice(60_000))
    chi2 = _chi_square(counts)
    assert chi2 < CHI2_DF5_P001, f"d6 not uniform: counts={counts}, chi2={chi2:.2f}"


def test_the_uniformity_test_can_actually_fail():
    """Guards the guard. A loaded die must trip the same assertion, or the
    test above proves nothing about the real roller."""
    loaded = [1] * 10_000 + [2, 3, 4, 5, 6] * 1_000
    assert _chi_square(_counts(loaded)) > CHI2_DF5_P001


def test_consecutive_rolls_are_independent():
    """Ordered pairs (previous, next) are uniform over all 36 combinations.
    A roller that never repeats a face, or alternates high and low, is in
    range and uniform per-face yet obviously unfair."""
    rolls = RandomRoller(seed=5).roll_dice(72_000)
    pairs = [0] * 36
    for a, b in zip(rolls, rolls[1:]):
        pairs[(a - 1) * 6 + (b - 1)] += 1
    chi2 = _chi_square(pairs)
    assert chi2 < CHI2_DF35_P001, f"pairs not independent: chi2={chi2:.2f}"


def test_the_mean_of_a_d6_is_three_and_a_half():
    rolls = RandomRoller(seed=6).roll_dice(60_000)
    mean = sum(rolls) / len(rolls)
    # Standard error of a d6 mean over 60k rolls is ~0.007; 5 sigma is ~0.035.
    assert math.isclose(mean, 3.5, abs_tol=0.035), f"mean was {mean}"


# ---------------------------------------------------------------------------
# Seed capture -- the part that makes a fight reproducible
# ---------------------------------------------------------------------------

def test_the_same_seed_gives_the_same_sequence():
    assert RandomRoller(seed=99).roll_dice(50) == RandomRoller(seed=99).roll_dice(50)


def test_different_seeds_give_different_sequences():
    assert RandomRoller(seed=1).roll_dice(50) != RandomRoller(seed=2).roll_dice(50)


def test_a_roller_reports_the_seed_it_was_given():
    assert RandomRoller(seed=4242).seed == 4242


def test_an_unseeded_roller_still_reports_a_real_seed():
    """The point of the whole exercise. `RandomRoller()` used to draw from OS
    entropy, so the seed did not exist as a value and no fight could be
    replayed afterwards. It must now choose a seed it can hand back."""
    roller = RandomRoller()
    assert isinstance(roller.seed, int)


def test_unseeded_rollers_do_not_all_share_one_seed():
    """Guards the guard: returning a constant would satisfy the test above
    and make every fight in the system roll identically."""
    seeds = {RandomRoller().seed for _ in range(20)}
    assert len(seeds) == 20


def test_a_recorded_seed_replays_the_fight_exactly():
    """The feature, stated as a test: record `.seed` on the event log, and
    the whole sequence can be reproduced from the record alone."""
    live = RandomRoller()
    rolled = [live.roll_dice(6) for _ in range(40)]

    replay = RandomRoller(seed=live.seed)
    assert [replay.roll_dice(6) for _ in range(40)] == rolled
