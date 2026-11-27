"""Wounding (6E2 p.110), one of the lethality options a Gritty campaign turns on.

"A character who takes BODY damage for any reason must make an EGO Roll at
-1 for every full 2 BODY the character has taken. If the roll succeeds,
there's no effect beyond the damage normally done by the injury. If the
roll fails, the character can't take any offensive action in his next
Phase - he can't shoot, strike back, or use any offensive Combat Maneuver.
He may still move to Behind Cover, Dodge, or use any other neutral or
defensive Combat Maneuver."

RULING (Peter, 2026-11-27): "every full 2 BODY" is THIS hit's BODY, not
the running total --- each wound is its own flinch, as Western Hero p.154
frames it. A 3 always makes the roll and an 18 always fails it (6E1 p.57).

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from dataclasses import replace

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions.recording import resolve_attack_in_session
from kirby_combat.enumeration import LegalAction
from kirby_combat.models import AttackInput, AttackPower, DiceValues
from kirby_combat.session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_combat.wounds import flinching, wounding_target, without_offence
from kirby_dice import FakeRoller

BLAST = AttackPower(
    xmlid="ENERGYBLAST", name="Energy Blast", damage_dice=10, half_die=False,
    plus_one=False, damage_type="normal", defense_type="ed", range_m=200,
    uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
    increased_stun_mult=0, source_id=1,
)


def _man(id_, *, ego=15, attacks=()):
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=3, omcv=5, dmcv=5, spd=4, dex=20,
        ego=ego, str_=15, con=40, pre=15, rec=5, pd=0, ed=0, rpd=0, red=0,
        md=5, power_defense=0, flash_defense=0, max_stun=60, max_body=30,
        max_end=30, current_stun=60, current_body=30, current_end=30,
        attacks=list(attacks),
    )


def _rules(on: bool):
    return replace(CombatTemplate.default_6e_superheroic(), use_wounding=on)


def _session(template):
    return CombatSession.create(
        id="s", combatants=[_man("shooter", attacks=[BLAST]), _man("hit")],
        scene=None, template=template, dice_roller=FakeRoller([]),
    ).start()


def _shoot(session, template, wounding_roll):
    """10d6 at no defenses: 36 STUN, 11 BODY (so -5 on the EGO Roll)."""
    attack = AttackInput(
        attacker=session.combatants["shooter"], target=session.combatants["hit"],
        power=BLAST, distance_m=2, aim=None,
        dice=DiceValues(to_hit=[3, 3, 3], damage=[5, 4, 3, 6, 2, 4, 6, 3, 1, 2],
                        knockback=[6, 6]),
    )
    rolls = [wounding_roll] if wounding_roll else []
    session, result = resolve_attack_in_session(
        session, attack, template, roller=FakeRoller(rolls))
    return session, result


def test_the_roll_is_ego_less_one_per_full_two_body():
    """EGO 15 rolls 12-; 10 BODY is -5; 3 BODY is -1."""
    man = _man("m", ego=15)
    assert wounding_target(man, body_taken=10) == 7
    assert wounding_target(man, body_taken=3) == 11


def test_a_failed_roll_costs_his_offence_next_phase():
    rules = _rules(True)
    session, result = _shoot(_session(rules), rules, [4, 4, 4])   # 12 vs 7-
    assert result.body_dealt == 11
    row = session.event_log[-1].result_payload
    assert row["wounding"] == {"target_id": "hit", "roll": 12, "needed": 7,
                               "flinched": True}
    assert flinching(session, "hit")


def test_a_made_roll_costs_nothing():
    rules = _rules(True)
    session, _ = _shoot(_session(rules), rules, [1, 2, 3])          # 6 vs 7-
    assert session.event_log[-1].result_payload["wounding"]["flinched"] is False
    assert not flinching(session, "hit")


def test_the_flinch_lasts_one_phase_of_his():
    """On the live path: the loop offers him no attack in his next Phase,
    and the Phase after he may shoot again."""
    from kirby_combat.encounter import Encounter
    from kirby_combat.loop.run import run_phase
    from kirby_combat.squads import KEEP_ORDERS
    from fixtures.terms import terms_stated

    rules = _rules(True)
    session, _ = _shoot(terms_stated(_session(rules)), rules, [6, 6, 5])
    assert flinching(session, "hit")

    menus: list = []

    class _Watch:
        def give_orders(self, page):
            return KEEP_ORDERS

        def choose(self, situation):
            if situation.actor.id == "hit":
                menus.append({a.kind for a in situation.menu})
            idle = [a for a in situation.menu if a.kind == "dodge"]
            return (idle or situation.menu)[0].action_id

    encounter = Encounter(id="e", turn=1, segment=11, sessions=[session],
                          template=rules).run_segment(roller=lambda: [3, 3, 3])
    dice = FakeRoller([[3, 3, 3]] * 400)
    for _ in range(40):
        if len(menus) >= 2:
            break
        encounter = run_phase(encounter, _Watch(), roller=dice,
                              on_unresolvable="skip").encounter
    assert len(menus) >= 2, menus
    assert "attack" not in menus[0] and "dodge" in menus[0], menus[0]
    assert "attack" in menus[1], menus[1]


def test_off_the_rule_there_is_no_roll():
    rules = _rules(False)
    session, _ = _shoot(_session(rules), rules, None)
    assert "wounding" not in session.event_log[-1].result_payload


def test_flinching_he_may_dodge_and_take_cover_but_not_shoot():
    def offer(kind):
        return LegalAction(action_id=kind, kind=kind, target_id=None,
                           power_xmlid=None, power_name=None, summary=kind)

    menu = [offer(k) for k in ("attack", "multiple_attack", "dodge",
                                "move_to_cover", "half_move", "haymaker",
                                "set", "hide", "disarm")]
    assert {a.kind for a in without_offence(menu)} == {
        "dodge", "move_to_cover", "half_move", "hide"}


def test_his_page_says_he_is_flinching():
    from kirby_combat.brief_detail import _status_words as condition_words
    from kirby_combat.statuses import FLINCHING, statuses_for

    rules = _rules(True)
    session, _ = _shoot(_session(rules), rules, [6, 6, 6])
    assert FLINCHING in statuses_for(session, "hit")
    assert any("flinching" in w for w in condition_words(session, "hit"))
