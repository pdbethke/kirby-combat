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
    # 10d6 sum 35, less MD 3 = 32 -> EGO + 22 -> "contrary"; the order
    # `withdraw` needs EGO+20 = 30, so it takes hold.
    result = resolve_mind_control(
        attacker=a, target=t,
        effect_dice_values=[4, 4, 4, 4, 3, 3, 4, 3, 3, 3],   # sums to 35
        order="withdraw",
    )
    assert isinstance(result, MindControlResult)
    assert (result.effect_rolled, result.effect_total) == (35, 32)
    assert result.degree == "contrary"
    assert result.target_ego == 10
    assert (result.required_total, result.established) == (30, True)


@pytest.mark.parametrize("order,level", [("spare", 10), ("withdraw", 20), ("turn", 30)])
def test_each_order_needs_the_level_the_book_gives_its_combat_example(order, level):
    """6E1 p.256: a poor choice of target at EGO+10, fleeing the combat at
    EGO+20, attacking an ally beyond that. One short of the total is no
    effect at all (p.255)."""
    from kirby_combat.mental.mind_control import ORDERS

    assert ORDERS[order] == level
    t = _target(ego=10)          # MD 3
    need = 10 + level + 3
    hit = resolve_mind_control(_mentalist(), t, [need], order=order)
    miss = resolve_mind_control(_mentalist(), t, [need - 1], order=order)
    assert hit.established and not miss.established
    assert miss.breakout_modifier == 0


def test_the_breakout_roll_takes_minus_one_per_five_over_the_minimum():
    """6E1 p.152's own example: aiming for EGO+20 and rolling EGO+30 puts
    the Breakout Roll at -2."""
    from kirby_combat.mental.mind_control import breakout_modifier

    assert breakout_modifier(40, 30) == -2
    assert breakout_modifier(34, 30) == 0
    assert breakout_modifier(35, 30) == -1
    t = _target(ego=10)          # needs 10 + 20 + 3 = 33 for withdraw
    r = resolve_mind_control(_mentalist(), t, [43], order="withdraw")
    assert r.breakout_modifier == -2


def test_an_order_the_engine_does_not_know_is_refused():
    with pytest.raises(ValueError, match="unknown Mind Control order"):
        resolve_mind_control(_mentalist(), _target(), [30], order="obey")


def test_mind_control_target_can_break_out_each_phase_with_ego_roll():
    # EGO 10 -> 9 + EGO/5 = 11- on 3d6 to break out (6E1 p41 char rolls)
    t = _target(ego=10)
    state = MindControlState(target_id=t.id, degree="simple", effect_total=20)
    # roll 11 -> succeeds (4+4+3)
    assert can_break_out_with_ego_roll(t, [4, 4, 3]) is True
    # roll 12 -> fails (need 11 or less)
    assert can_break_out_with_ego_roll(t, [4, 4, 4]) is False


def test_mind_control_break_out_ego_roll_rounds_like_canon():
    """EGO 18 gives a 13- Characteristic Roll, not 12-. The two formulas
    disagree on 16 of 40 characteristic values and this site had the
    truncating one (9 + EGO // 5). A roll of 13 distinguishes them:
    canon (13-) succeeds; truncated (12-) fails."""
    t = _target(ego=18)
    assert can_break_out_with_ego_roll(t, [5, 4, 4]) is True   # 13 <= 13-
