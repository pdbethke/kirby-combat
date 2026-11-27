"""Impairing and Disabling wounds, and Knockdown (6E2 p.113-115).

"Whenever the BODY damage done to an area ... is more than half the
character's total BODY, that area is Impaired"; more than his total BODY,
Disabled. Effects in the fight from Western Hero's table (p.154): a head is
Knocked Out (to -10 STUN), an arm -3 OCV with attacks using it, the torso
no Post-Segment 12 Recovery, a leg -2 DCV. Knockdown (p.114): an Impairing
wound is a DEX Roll or fall, a Disabling one puts him down.

RULINGS (Peter, 2026-11-27): head and torso effects only on a failed CON
Roll; the arm hit is the side facing the shooter, and a man stands bladed
toward whoever he last attacked, gun hand forward.

Gunmen are built through `build_from_json` with real Accessible Foci, so
grips and weapons are found as a corpus character's are.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from kirby_dice import FakeRoller

from tests.conftest_grips import gun, gunman, session_of, weapon_id
from kirby_combat.actions.recording import _fold_session_cvs, resolve_attack_in_session
from kirby_combat.cv_modifiers import effective_dcv_for
from kirby_combat.grips import Grip, LEFT, RIGHT, state_grips
from kirby_combat.models import AttackInput, DiceValues
from kirby_combat.statuses import PRONE, statuses_for
from kirby_combat.template import RAW_HEROIC
from kirby_combat.wounds import WOUND, active_wounds

RULES = replace(RAW_HEROIC, use_impairing_disabling=True, use_knockdown=False,
                use_knockback=False)


@pytest.fixture(autouse=True)
def _template_needed():
    from tests.corpus import require_template
    require_template()


def _fight(rules=RULES):
    shooter = gunman("shooter", gun("big", "Big Gun", levels=4), side="b")
    hit = gunman("hit", gun("colt", "Colt"), gun("derringer", "Derringer"))
    session = session_of(shooter, hit, template=rules)
    session = state_grips(session, "shooter", [Grip(weapon_id(shooter, "Big Gun"), RIGHT)])
    session = state_grips(session, "hit", [Grip(weapon_id(hit, "Colt"), RIGHT),
                                           Grip(weapon_id(hit, "Derringer"), LEFT)])
    return session


def _shoot(session, where, body_dice, rolls, rules=RULES, by="shooter", at="hit"):
    shooter = session.combatants[by]
    attack = AttackInput(
        attacker=shooter, target=session.combatants[at], power=shooter.attacks[0],
        distance_m=2, aim=where,
        dice=DiceValues(to_hit=[1, 1, 1], damage=list(body_dice), stun_multiplier=[1]))
    session, result = resolve_attack_in_session(session, attack, rules, roller=FakeRoller(rolls))
    return session, result, session.event_log[-1].result_payload


def test_an_arm_wound_over_half_his_body_is_impaired():
    """4d6 at 12 BODY, x1/2 for the Arm: 6 against 10 BODY."""
    session, result, row = _shoot(_fight(), "Arm", [3, 3, 3, 3], [[2]])
    assert result.body_dealt == 6
    assert row[WOUND]["severity"] == "impaired" and row[WOUND]["took_effect"]
    assert row[WOUND]["side"] == RIGHT, "no attack yet: he presents his first gun's hand"


def test_under_half_is_no_wound():
    session, result, row = _shoot(_fight(), "Arm", [2, 2, 3, 3], [])
    assert result.body_dealt == 5 and WOUND not in row


def test_the_wounded_arm_spoils_the_gun_in_it_and_not_the_other():
    session, _, _ = _shoot(_fight(), "Arm", [3, 3, 3, 3], [[2]])
    hit = session.combatants["hit"]
    colt = next(p for p in hit.attacks if p.name == "Colt")
    derringer = next(p for p in hit.attacks if p.name == "Derringer")

    def ocv(power):
        attack = AttackInput(attacker=hit, target=session.combatants["shooter"],
                             power=power, distance_m=2, aim=None, dice=DiceValues())
        return _fold_session_cvs(session, attack).ocv_modifier

    assert ocv(colt) - ocv(derringer) == -3


def test_a_leg_wound_is_minus_two_dcv():
    """Against the same shot with the rule off, so a Stun from the blow
    (6E2 p.106, half DCV) is on both sides of the comparison."""
    off = replace(RULES, use_impairing_disabling=False)
    plain, _, _ = _shoot(_fight(off), "Leg", [3, 3, 3, 3], [], rules=off)
    wounded, _, row = _shoot(_fight(), "Leg", [3, 3, 3, 3], [[2]])
    assert row[WOUND]["region"] == "leg"

    def dcv(session):
        return effective_dcv_for(session, "hit", against="shooter", combat_type="ranged")

    assert (dcv(plain), dcv(wounded)) == (2, 0)


def test_a_head_wound_takes_effect_only_on_a_failed_con_roll():
    """Head BODYx 2: 3 BODY rolled is 6. CON 10 rolls 11-."""
    made, _, row = _shoot(_fight(), "Head", [1, 1, 1, 0], [[1, 2, 3], [2]])
    assert row[WOUND]["took_effect"] is False
    failed, _, row = _shoot(_fight(), "Head", [1, 1, 1, 0], [[6, 6, 5], [2]])
    assert row[WOUND]["took_effect"] is True
    assert failed.combatants["hit"].state.current_stun <= -10, "Knocked Out, to -10 STUN"


def test_a_torso_wound_stops_the_post_twelve_recovery():
    from kirby_combat.encounter import _apply_post_12_recovery

    session, _, row = _shoot(_fight(), "Chest", [3, 3, 0, 0], [[6, 6, 6], [4]])
    assert row[WOUND]["region"] == "torso" and row[WOUND]["took_effect"]
    after = _apply_post_12_recovery(session, RULES)
    taken = {e.combatant_id: e.stun_recovered for e in after.event_log
             if e.kind == "RecoveryTaken"}
    assert taken["hit"] == 0
    assert taken["shooter"] == 0, "he is at full STUN: nothing to recover either way"


def test_a_one_turn_impairment_wears_off():
    session, _, _ = _shoot(_fight(), "Leg", [3, 3, 3, 3], [[1]])     # 1: 1 Turn
    assert active_wounds(session, "hit")
    from kirby_combat.encounter import Encounter

    encounter = Encounter(id="e", turn=1, segment=12, sessions=[session], template=RULES)
    for _ in range(12):
        encounter = encounter.advance_segment()
    assert not active_wounds(encounter.sessions[0], "hit")


def test_a_disabling_wound_knocks_him_down():
    """24 BODY x 1/2 = 12, over his 10."""
    rules = replace(RULES, use_knockdown=True)
    session, _, row = _shoot(_fight(rules), "Leg", [6, 6, 6, 6], [], rules=rules)
    assert row[WOUND]["severity"] == "disabled"
    assert row[WOUND]["knockdown"]["fell"] is True
    assert PRONE in statuses_for(session, "hit")


def test_an_impairing_wound_is_a_dex_roll_or_fall():
    rules = replace(RULES, use_knockdown=True)
    kept, _, row = _shoot(_fight(rules), "Leg", [3, 3, 3, 3], [[2], [1, 2, 3]], rules=rules)
    assert row[WOUND]["knockdown"]["fell"] is False
    fell, _, row = _shoot(_fight(rules), "Leg", [3, 3, 3, 3], [[2], [6, 6, 5]], rules=rules)
    assert PRONE in statuses_for(fell, "hit")


def test_off_the_rule_there_is_no_wound():
    rules = replace(RULES, use_impairing_disabling=False)
    _, _, row = _shoot(_fight(rules), "Arm", [6, 6, 6, 6], [], rules=rules)
    assert WOUND not in row
