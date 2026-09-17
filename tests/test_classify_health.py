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


# ---------------------------------------------------------------------------
# The fourth and fifth copies, closed 2026-09-17
# ---------------------------------------------------------------------------

def _recover_offered(actor) -> bool:
    from kirby_combat.enumeration import enumerate_actions

    return any(a.kind == "recover"
               for a in enumerate_actions(actor, [], has_scene=False))


def _fighter(*, stun: int, max_stun: int, end: int = 40):
    return synthetic_combatant(
        id="a", name="a", spd=4, dex=20, max_stun=max_stun, max_body=12,
        max_end=40, current_stun=stun, current_body=12, current_end=end,
        rec=6,
    )


@pytest.mark.parametrize("stun,max_stun", [
    (40, 40),           # untouched
    (20, 40),           # exactly half -- healthy, and no Recover
    (19, 40),           # below half -- wounded
    (10, 40),           # a quarter -- critical
    # THE CASE THE TWO COPIES REALLY DISAGREED ON. `max_stun // 2` is 22
    # and half of 45 is 22.5, so 22 STUN is BELOW half by the percentage
    # and NOT below it by the integer division: the menu called him
    # healthy enough to skip the offer while `classify_health` called him
    # wounded. 45 is an ordinary STUN total, not a contrivance.
    (22, 45),
    (23, 45),
])
def test_the_recover_offer_stands_on_the_same_rung_as_the_ladder(stun, max_stun):
    """The menu and the tactic layer read one number one way.

    `enumerate_actions` held the fourth copy of the ladder --- and the
    only one written in integer division rather than the rounded
    percentage, which is why it could differ for a real fighter rather
    than only in principle.
    """
    actor = _fighter(stun=stun, max_stun=max_stun)

    assert _recover_offered(actor) is (classify_health(actor) != "healthy")


def test_a_healthy_man_low_on_end_is_still_offered_a_recovery():
    """The END half of the offer is NOT a health rung, and stays put.

    `classify_health` knows nothing about END on purpose. A fresh fighter
    who has spent his END is not wounded by any reading, and must still
    be able to sit down and get his wind back (6E2 p.130).
    """
    actor = _fighter(stun=40, max_stun=40, end=3)

    assert classify_health(actor) == "healthy"
    assert _recover_offered(actor) is True


def test_the_bricks_posture_asks_the_shared_ladder_too():
    """`stand_and_take_it` kept the fifth copy: its own 50% and its own
    `current_body <= 0`. Its "healthy" is the ladder's "healthy"."""
    from kirby_combat.tactics.catalog.stand_and_take_it import StandAndTakeIt

    tactic = StandAndTakeIt()
    for stun, expected in ((40, True), (20, True), (19, False), (10, False)):
        actor = synthetic_combatant(
            id="brick", name="brick", spd=4, dex=20, pd=15, ed=15,
            max_stun=40, max_body=12, max_end=40,
            current_stun=stun, current_body=12, current_end=40,
        )
        situation = Situation(actor=actor, allies=[], enemies=[])
        assert tactic.applicable(situation) is expected
        assert (classify_health(actor) == "healthy") is expected


def test_the_brick_with_no_stun_track_still_does_not_stand():
    """The one place the two answers are allowed to differ, said out loud.

    `classify_health` calls a man with no STUN maximum "healthy" --- there
    is no ladder to place him on. A posture about absorbing STUN needs a
    STUN track, so the tactic refuses anyway, and that refusal lives in
    the tactic rather than in the ladder.
    """
    from kirby_combat.tactics.catalog.stand_and_take_it import StandAndTakeIt

    actor = synthetic_combatant(
        id="brick", name="brick", spd=4, dex=20, pd=15, ed=15,
        max_stun=0, max_body=12, max_end=40,
        current_stun=0, current_body=12, current_end=40,
    )

    assert classify_health(actor) == "healthy"
    assert StandAndTakeIt().applicable(
        Situation(actor=actor, allies=[], enemies=[])) is False


@pytest.mark.parametrize("stun,max_stun,expected", [
    (19, 40, 48), (10, 40, 25), (0, 40, 0), (40, 40, 100), (0, 0, 0),
])
def test_stun_percent_is_the_number_the_ladder_is_cut_from(
    stun, max_stun, expected,
):
    from kirby_combat.health import stun_percent

    assert stun_percent(_Body(stun, max_stun)) == expected


def test_the_rationale_says_the_percentage_the_tactic_turned_on():
    """Both hurt-tactics printed a percentage they recomputed themselves."""
    from kirby_combat.health import stun_percent
    from kirby_combat.tactics.catalog.reposition_when_spotted import (
        RepositionWhenSpotted,
    )

    from kirby_combat.models import AttackPower

    blast = AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=8, half_die=False,
        plus_one=False, damage_type="normal", defense_type="ed",
        range_m=100.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, source_id="a-eb",
        is_ranged=True,
    )
    actor = synthetic_combatant(
        id="a", name="a", spd=4, dex=20, max_stun=40, max_body=12,
        max_end=40, current_stun=19, current_body=12, current_end=40,
        rec=6, attacks=[blast],
    )
    enemy = _fighter(stun=40, max_stun=40)
    situation = Situation(actor=actor, allies=[], enemies=[enemy])
    pct = stun_percent(actor)

    assert f"{pct}% STUN" in TakeCoverWhenHurt().execute(situation).rationale
    assert RepositionWhenSpotted().applicable(situation), \
        "the ranged tactic must actually fire, or the assertion below is empty"
    assert f"{pct}% STUN" in \
        RepositionWhenSpotted().execute(situation).rationale
