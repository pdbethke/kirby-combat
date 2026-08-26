"""Mind Control — degree ladder + EGO+N rolls. 6E1 pg 101."""
import pytest

from kirby_combat.mental.mind_control import (
    mind_control_degree, resolve_mind_control,
    MindControlResult, MindControlState,
    can_break_out_with_ego_roll,
)
from tests.fixtures.synthetic_hero import synthetic_combatant


def _mentalist(id_: str = "a"):
    return synthetic_combatant(
        id=id_, name=id_, ocv=0, dcv=0, omcv=8, dmcv=3,
        spd=4, dex=15, ego=18, str_=10, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=40,
        current_stun=30, current_body=15, current_end=40,
        is_mentalist=True,
    )


def _target(id_: str = "t", ego: int = 10):
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=3, dmcv=5,
        spd=3, dex=12, ego=ego, str_=15, con=15, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=3, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def test_mind_control_degree_ego_plus_0_is_ego_push():
    # roll 10 vs EGO 10 -> margin 0 -> ego_push
    assert mind_control_degree(10, 10) == "ego_push"


def test_mind_control_degree_ego_plus_10_is_simple():
    assert mind_control_degree(20, 10) == "simple"


def test_mind_control_degree_ego_plus_30_is_violent():
    assert mind_control_degree(40, 10) == "violent"


def test_mind_control_below_ego_is_none():
    # roll 9 vs EGO 10 -> margin -1 -> none
    assert mind_control_degree(9, 10) == "none"


def test_mind_control_resolves_full_action_with_effect_and_degree():
    a = _mentalist()
    t = _target(ego=10)
    # 10d6 mind control, dice sum to 35 -> EGO + 25 -> "contrary"
    result = resolve_mind_control(
        attacker=a, target=t,
        effect_dice_values=[4, 4, 4, 4, 3, 3, 4, 3, 3, 3],   # sums to 35
    )
    assert isinstance(result, MindControlResult)
    assert result.effect_total == 35
    assert result.degree == "contrary"
    assert result.target_ego == 10


def test_mind_control_target_can_break_out_each_phase_with_ego_roll():
    # EGO 10 -> 9 + EGO/5 = 11- on 3d6 to break out (6E1 p41 char rolls)
    t = _target(ego=10)
    state = MindControlState(target_id=t.id, degree="simple", effect_total=20)
    # roll 11 -> succeeds (4+4+3)
    assert can_break_out_with_ego_roll(t, [4, 4, 3]) is True
    # roll 12 -> fails (need 11 or less)
    assert can_break_out_with_ego_roll(t, [4, 4, 4]) is False
