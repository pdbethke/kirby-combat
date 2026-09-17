"""The health ladder, at its rungs — and only one statement of it.

`classify_health` is the engine's JUDGEMENT about when a fighter is hurt
enough to change what he does; 6E names no such state. It had stood as
three private copies of the same five lines, one per consumer, which is
three judgements wearing one name. These tests pin the rungs AT the
boundaries (where a copy drifts first) and pin the two tactics to the
shared function rather than to their own arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from fixtures.synthetic_hero import synthetic_combatant

from kirby_combat import classify_health
from kirby_combat.tactics.base import Situation
from kirby_combat.tactics.catalog.take_cover_when_hurt import TakeCoverWhenHurt


@dataclass
class _Body:
    """The four live numbers the ladder reads. Both real combatant shapes
    answer these same names (`HeroCombatant` as properties off `state`)."""
    current_stun: int
    max_stun: int
    current_body: int = 12
    max_body: int = 12


@pytest.mark.parametrize("stun,max_stun,body,max_body,expected", [
    # Untouched.
    (40, 40, 12, 12, "healthy"),
    # EXACTLY half: healthy. "wounded" is BELOW half, not at it -- the
    # Recover offer reads the same rung the same way ("<½ STUN").
    (20, 40, 12, 12, "healthy"),
    (19, 40, 12, 12, "wounded"),
    # EXACTLY a quarter: critical. This rung is inclusive and the one
    # above it is not, which is exactly the asymmetry a second copy of
    # this arithmetic gets wrong.
    (10, 40, 12, 12, "critical"),
    (11, 40, 12, 12, "wounded"),
    # BODY at zero is critical however much STUN is left (6E1 p.421 --
    # dying is not a matter of degree).
    (40, 40, 0, 12, "critical"),
    (40, 40, -3, 12, "critical"),
    # STUN at zero or below.
    (0, 40, 12, 12, "critical"),
    (-5, 40, 12, 12, "critical"),
    # Rounding is on the percentage, not the ratio: 24.5% of 200 rounds
    # to 25 and lands on the critical rung.
    (49, 200, 12, 12, "critical"),
    (51, 200, 12, 12, "wounded"),
])
def test_the_rungs(stun, max_stun, body, max_body, expected):
    assert classify_health(
        _Body(stun, max_stun, body, max_body)) == expected


def test_no_stun_maximum_is_not_a_division():
    """A combatant with no STUN maximum has no ladder to stand on.

    Pinned rather than merely working: the existing behaviour was to
    treat him as at his default health, and the alternative -- a
    ZeroDivisionError from a tactic's `applicable` -- would take the
    whole menu down.
    """
    assert classify_health(_Body(0, 0, 12, 12)) == "healthy"
    assert classify_health(_Body(-9, 0, 0, 0)) == "healthy"


def test_no_body_maximum_is_not_a_division_either():
    assert classify_health(_Body(40, 40, 5, 0)) == "healthy"
    assert classify_health(_Body(40, 40, 0, 0)) == "critical"


def test_a_real_combatant_is_read_the_same_way():
    """The flat stub above and the HD-shaped participant answer alike."""
    def _c(stun: int):
        return synthetic_combatant(
            id="a", name="a", spd=4, dex=20, max_stun=40, max_body=12,
            max_end=40, current_stun=stun, current_body=12, current_end=40,
        )

    assert classify_health(_c(40)) == "healthy"
    assert classify_health(_c(19)) == "wounded"
    assert classify_health(_c(10)) == "critical"


def test_the_tactic_asks_the_shared_ladder():
    """One door: the tactic turns on exactly where the ladder says.

    It used to hold its own copy of the thresholds, so this could have
    been false without anything failing.
    """
    tactic = TakeCoverWhenHurt()
    for stun, expected in ((40, False), (20, False), (19, True), (10, True)):
        actor = _Body(stun, 40)
        situation = Situation(actor=actor, allies=[], enemies=[])
        assert tactic.applicable(situation) is expected
        assert (classify_health(actor) != "healthy") is expected
