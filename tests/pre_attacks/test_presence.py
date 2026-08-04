"""Presence attacks — PRE/5 dice, effects ladder."""
import pytest

from kirby_combat.pre_attacks import (
    resolve_presence_attack, base_pre_dice, can_act_after,
    PresenceAttackResult,
)
from kirby_combat.tables import presence_attack_effect, PRESENCE_ATTACK_EFFECTS
from fixtures.synthetic_hero import synthetic_combatant as Combatant


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
    """The 6E2 p138 Presence Attack Table, keyed on (roll - target PRE).

    6E2 p139, "attack equal to presence": "If the total on the Presence
    Attack dice AT LEAST EQUALS the target's PRE, the target is impressed."
    A margin of 0 is a LANDED attack, not a miss — this file previously
    asserted `no_effect` there, which put every tier 10 points too high and
    meant an attacker needed PRE+10 to buy the effect RAW grants at PRE+0.
    """
    assert presence_attack_effect(9, 10) == "no_effect"        # margin -1
    assert presence_attack_effect(10, 10) == "impressed"       # margin 0
    assert presence_attack_effect(19, 10) == "impressed"       # margin +9
    assert presence_attack_effect(20, 10) == "very_impressed"  # margin +10
    assert presence_attack_effect(30, 10) == "awed"            # margin +20
    assert presence_attack_effect(40, 10) == "cowed"           # margin +30
    assert presence_attack_effect(50, 10) == "overwhelmed"     # margin +40


def test_a_presence_attack_that_falls_short_does_nothing():
    # Below the target's PRE there is no entry on the table at all.
    assert presence_attack_effect(0, 20) == "no_effect"
    assert presence_attack_effect(19, 20) == "no_effect"


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
    # NOTE: this preserves the pre-existing MEANING (only the worst tier
    # stops the target acting) under the corrected names. RAW 6E2 p139 is
    # stricter — at PRE+20 "awed" the target "will not act for 1 Full
    # Phase" — but wiring the table's mechanical consequences is a separate
    # piece of work from correcting the table itself.
    assert can_act_after("overwhelmed") is False
    assert can_act_after("cowed") is False
    assert can_act_after("awed") is True
    assert can_act_after("very_impressed") is True
    assert can_act_after("impressed") is True
