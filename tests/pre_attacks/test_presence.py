"""Presence attacks — PRE/5 dice, effects ladder."""
import pytest

from kirby_combat.pre_attacks import (
    resolve_presence_attack, base_pre_dice, can_act_after,
    PresenceAttackResult,
)
from kirby_combat.tables import presence_attack_effect, PRESENCE_ATTACK_EFFECTS
from kirby_combat.models import Combatant


def _attacker(pre: int = 25) -> Combatant:
    return Combatant(
        id="a", name="a", ocv=8, dcv=8, omcv=3, dmcv=3,
        spd=4, dex=15, ego=15, str_=20, con=15, pre=pre, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _target(pre: int = 10) -> Combatant:
    return Combatant(
        id="t", name="t", ocv=8, dcv=8, omcv=3, dmcv=3,
        spd=4, dex=15, ego=15, str_=15, con=15, pre=pre, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def test_presence_attack_computes_dice_from_pre_divided_by_5():
    a = _attacker(pre=25)
    assert base_pre_dice(a) == 5
    a2 = _attacker(pre=37)
    assert base_pre_dice(a2) == 7    # 37//5 = 7


def test_presence_attack_reduced_by_target_pre_defense():
    a = _attacker(pre=25)   # 5 dice
    t = _target(pre=10)
    r = resolve_presence_attack(a, t, dice_values=[4, 4, 4, 4, 4],
                                target_pre_defense=2)
    # 5 - 2 = 3 effective dice; sum = 12
    assert r.effective_dice == 3
    assert r.roll_total == 12


def test_presence_effect_ladder_thresholds():
    # Sanity-check the table itself; margins are relative to target PRE
    assert presence_attack_effect(9, 10) == "no_effect"     # margin -1
    assert presence_attack_effect(10, 10) == "no_effect"    # margin 0
    assert presence_attack_effect(20, 10) == "hesitation"   # margin 10
    assert presence_attack_effect(30, 10) == "impressed"    # margin 20
    assert presence_attack_effect(40, 10) == "fear"         # margin 30
    assert presence_attack_effect(50, 10) == "cower"        # margin 40


def test_presence_attack_bonus_dice_from_appropriate_situation():
    a = _attacker(pre=25)   # 5 base dice
    t = _target(pre=10)
    r = resolve_presence_attack(
        a, t, dice_values=[4] * 8, bonus_dice_from_situation=3,
    )
    # 5 + 3 = 8 dice
    assert r.total_dice == 8
    assert r.effective_dice == 8


def test_presence_attack_no_direct_damage():
    a = _attacker(pre=25)
    t = _target(pre=10)
    r = resolve_presence_attack(a, t, dice_values=[4] * 5)
    assert not hasattr(r, "stun_dealt")
    assert not hasattr(r, "body_dealt")


def test_targets_cower_result_cannot_act_this_turn():
    assert can_act_after("cower") is False
    assert can_act_after("fear") is True
    assert can_act_after("hesitation") is True
