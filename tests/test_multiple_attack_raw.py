"""Multiple Attack against the book's own worked examples (6E2 p.73-74).

The engine used to give a DESCENDING ladder -- shot 1 at full OCV, shot 2
at -2, shot 3 at -4 -- on the reading that "each attack after the first
takes a cumulative -2". The page's three worked examples all say
otherwise: the penalty grows with the NUMBER of attacks and then applies
to EVERY Attack Roll in the sequence, the first one included.

That difference is why a model spammed the maneuver. A descending ladder
makes Multiple Attack strictly better than a single attack -- the first
shot is identical, and the rest are free. The flat penalty is the price
the book charges, and with it the choice is a real one.

The second rule on the same page is the other half of the price: miss any
roll and every remaining attack in the sequence automatically misses.

Examples paraphrased; this project ships no rules text.
"""
from __future__ import annotations

import pytest

from kirby_combat.actions.multiple_attack import MultipleAttack
from kirby_combat.actions.sweep import Sweep


def _ocvs(base, n, csl=0):
    return MultipleAttack.compute(base_ocv=base, num_targets=n,
                                  csl_offset=csl).per_shot_ocv


def test_five_attacks_take_minus_eight_on_every_roll():
    """6E2 p.73. A hero splits a Blast and a Flash across three foes for
    five attacks in all, and the page works the penalty as (5-1) x -2 =
    -8, applied to each Attack Roll -- not to the last one only."""
    assert _ocvs(10, 5) == [2, 2, 2, 2, 2]


def test_three_shots_take_minus_four_on_all_three():
    """6E2 p.74. A character fires three rifle shots at one target and
    the page states a -4 OCV on all three shots."""
    assert _ocvs(9, 3) == [5, 5, 5]


def test_four_attacks_take_minus_six():
    """6E2 p.73. Four attacks spread over three targets: -6 on all."""
    assert _ocvs(8, 4) == [2, 2, 2, 2]


def test_a_multiple_move_by_stacks_its_own_penalty():
    """6E2 p.74. Three henchmen attacked with Move Bys: -4 for the three
    attacks, plus -2 for the Move By itself, leaving OCV 3 from a base
    of 9. The maneuver's own -2 is the caller's to add; what this checks
    is that the Multiple Attack half contributes -4 and not -0/-2/-4."""
    assert _ocvs(9, 3) == [5, 5, 5]
    assert [o - 2 for o in _ocvs(9, 3)] == [3, 3, 3]


def test_one_attack_is_unpenalised():
    """(1-1) x -2 is zero. A Multiple Attack of one is a plain attack."""
    assert _ocvs(7, 1) == [7]


def test_combat_skill_levels_buy_the_penalty_down():
    """Levels allocated to OCV offset the penalty, and cannot push OCV
    above the base -- three attacks is -4, so two levels leave -2."""
    assert _ocvs(9, 3, csl=2) == [7, 7, 7]
    assert _ocvs(9, 3, csl=99) == [9, 9, 9]


def test_sweep_charges_the_same_price():
    """Sweep delegates to the same arithmetic, so it moves with it."""
    assert Sweep.compute(base_ocv=9, num_targets=3).per_shot_ocv == [5, 5, 5]


def test_the_penalty_is_flat_not_descending():
    """The regression guard, stated directly: every shot at one OCV."""
    for n in range(1, 8):
        ocvs = _ocvs(12, n)
        assert len(set(ocvs)) == 1, f"{n} attacks gave a ladder: {ocvs}"
        assert ocvs[0] == 12 - 2 * (n - 1)
