"""Mental Illusion — degree + disbelief."""
import pytest

from kirby_combat.mental.mental_illusion import (
    resolve_mental_illusion, attempt_disbelief,
    MentalIllusionResult, DisbeliefResult,
)
from kirby_combat.models import Combatant


def _mentalist(id_: str = "a") -> Combatant:
    return Combatant(
        id=id_, name=id_, ocv=0, dcv=0, omcv=8, dmcv=3,
        spd=4, dex=15, ego=18, str_=10, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=40,
        current_stun=30, current_body=15, current_end=40,
        is_mentalist=True,
    )


def _target(id_: str = "t", ego: int = 10) -> Combatant:
    return Combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=3, dmcv=5,
        spd=3, dex=12, ego=ego, str_=15, con=15, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=3, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def test_mental_illusion_degree_ladder_simple_to_elaborate():
    a = _mentalist()
    t = _target(ego=10)
    r = resolve_mental_illusion(a, t, [3] * 10)   # 30, margin 20 -> elaborate
    assert r.degree == "elaborate"
    r_simple = resolve_mental_illusion(a, t, [4, 3, 3])  # 10, margin 0 -> simple
    assert r_simple.degree == "simple"
    r_perfect = resolve_mental_illusion(a, t, [4] * 10)  # 40, margin 30 -> perfect
    assert r_perfect.degree == "perfect"


def test_mental_illusion_target_can_disbelieve_on_contradiction():
    t = _target(ego=10)
    # No contradiction observed -> no check
    r_no = attempt_disbelief(t, illusion_effect_total=15, ego_roll_dice=[3, 3, 3],
                             contradiction_observed=False)
    assert r_no.illusion_ended is False
    assert r_no.success is False


def test_mental_illusion_ego_roll_vs_ego_plus_effect_to_disbelieve():
    t = _target(ego=10)
    # base TN = 9 + 10/5 = 11; illusion margin = 15-10 = 5; effective TN = 6
    # roll 6 -> succeeds
    r = attempt_disbelief(t, illusion_effect_total=15, ego_roll_dice=[2, 2, 2],
                          contradiction_observed=True)
    assert r.target_number == 6
    assert r.success is True
    # roll 7 -> fails
    r2 = attempt_disbelief(t, illusion_effect_total=15, ego_roll_dice=[3, 2, 2],
                           contradiction_observed=True)
    assert r2.success is False


def test_mental_illusion_ends_on_disbelief_success():
    t = _target(ego=10)
    r = attempt_disbelief(t, illusion_effect_total=10, ego_roll_dice=[3, 3, 3],
                          contradiction_observed=True)
    # base TN 11, no margin penalty, roll 9 -> success
    assert r.success is True
    assert r.illusion_ended is True


def test_mental_illusion_does_not_directly_damage():
    a = _mentalist()
    t = _target(ego=10)
    r = resolve_mental_illusion(a, t, [4, 3, 3])
    assert not hasattr(r, "stun")
    assert not hasattr(r, "body")
