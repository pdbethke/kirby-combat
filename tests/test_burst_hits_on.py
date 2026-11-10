"""`burst_hits_on`: 6E2 p.44's count read off the engine's own to-hit answer.

One public home for it, because two callers need it: the burst resolver, and
kirby-ai's EV seat, which prices a burst before it is fired. A seat that
re-derived the count would carry its own copy of the natural-3 rule
(6E2 p.37: a 3 always hits, so a hit can have a negative margin), and two
copies drift.
"""
from types import SimpleNamespace

import pytest

from kirby_combat.actions.autofire import burst_hits_on


def _roll(hit: bool, margin: int):
    return SimpleNamespace(hit=hit, margin=margin)


@pytest.mark.parametrize("margin, shots, hits", [
    (0, 5, 1), (1, 5, 1), (2, 5, 2), (7, 5, 4), (8, 5, 5), (20, 5, 5), (6, 3, 3),
])
def test_one_hit_plus_one_per_full_two_points(margin, shots, hits) -> None:
    assert burst_hits_on(_roll(True, margin), shots) == hits


def test_a_miss_hits_nothing() -> None:
    assert burst_hits_on(_roll(False, -1), 5) == 0


def test_a_natural_three_with_a_negative_margin_hits_once() -> None:
    assert burst_hits_on(_roll(True, -4), 5) == 1
