"""An attack built from a character costs the END its sheet says.

The engine recomputed an attack's END from its Active Points and knew
Reduced Endurance only as "on", so every ½ END power cost NOTHING: 186 of
the 2,585 attacks in the local character library. 6E1 p.347: "½ END
Reduced Endurance ... costs 1 END per 20 Active Points", the Advantage
itself excluded. Two more kinds disagreed with Hero Designer: Charges that
also Cost Endurance (they pay END too) and the slots of a Multipower whose
reserve carries Charges (they pay none).

Hero Designer's END column is the cost engine's own `end_usage` (kirby-cost,
oracle parity), so a built attack carries it (`AttackPower.end_per_use`)
and `endurance.end_cost` reads it, as movement does since 0.24.0. An attack
stated by hand (a synthetic fighter, a martial maneuver) still prices from
its stated Active Points.
"""
from __future__ import annotations

import pytest

from kirby_combat.endurance import end_cost
from tests.corpus import require_template

_CHARS = [{"xmlid": x, "levels": 0} for x in (
    "STR", "DEX", "CON", "BODY", "STUN", "END", "SPD", "PD", "ED", "REC", "OCV", "DCV")]


def _attacks(*powers):
    from kirby_cost.io.build_json import build_from_json

    from kirby_combat.hero_view import HeroCombatant

    hero = build_from_json({
        "name": "Blaster", "template": "Main6E",
        "base_points": 400, "disad_points": 75, "experience": 0,
        "characteristics": _CHARS, "powers": list(powers),
        "skills": [], "perks": [], "talents": [], "disadvantages": [],
    })
    return {a.name: a for a in HeroCombatant.from_build(hero, id="b").attacks}


def _blast(name, *modifiers):
    return {"id": name, "xmlid": "ENERGYBLAST", "name": name, "levels": 12,
            "input": "ED", "modifiers": list(modifiers)}


@pytest.fixture(autouse=True)
def _template():
    require_template()


def test_half_end_costs_half():
    """12d6 is 60 Active Points: 6 END, and at ½ END one per 20 of the 60
    --- 3 (the Advantage's own points are not counted)."""
    attacks = _attacks(
        _blast("Full"),
        _blast("Half", {"id": "h", "xmlid": "REDUCEDEND", "option_id": "HALFEND"}),
        _blast("Free", {"id": "z", "xmlid": "REDUCEDEND", "option_id": "ZERO"}),
    )
    assert [end_cost(attacks[n]) for n in ("Full", "Half", "Free")] == [6, 3, 0]


def test_charges_that_cost_endurance_pay_it():
    attacks = _attacks(_blast(
        "Clip", {"id": "c", "xmlid": "CHARGES", "option_id": "SIXTEEN"},
        {"id": "e", "xmlid": "COSTSEND", "option_id": "EVERYPHASE"}))
    assert end_cost(attacks["Clip"]) > 0


def test_a_hand_stated_attack_still_prices_from_its_points():
    from kirby_combat.models import AttackPower

    stated = AttackPower(
        xmlid="ENERGYBLAST", name="b", damage_dice=12, half_die=False,
        plus_one=False, damage_type="normal", defense_type="ed", range_m=100,
        uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
        increased_stun_mult=0, active_points=60)
    assert stated.end_per_use is None
    assert end_cost(stated) == 6


# ---------------------------------------------------------------------------
# A Multipower's Charges are one supply for every slot
# ---------------------------------------------------------------------------

def _rifle():
    """Lazer's rifle in small: a Multipower whose reserve carries the
    Charges, two blast slots under it (6E1 p.409)."""
    from kirby_cost.io.build_json import build_from_json

    return build_from_json({
        "name": "Lazer", "template": "Main6E",
        "base_points": 400, "disad_points": 75, "experience": 0,
        "characteristics": _CHARS,
        "powers": [
            {"id": "MP", "xmlid": "MULTIPOWER", "name": "Rifle", "base_cost": 60.0,
             "modifiers": [{"id": "c", "xmlid": "CHARGES", "option_id": "FOUR"}]},
            {"id": "S1", "xmlid": "ENERGYBLAST", "name": "Stun Setting", "levels": 8,
             "input": "ED", "parent": "MP"},
            {"id": "S2", "xmlid": "ENERGYBLAST", "name": "Kill Setting", "levels": 8,
             "input": "ED", "parent": "MP"},
        ],
        "skills": [], "perks": [], "talents": [], "disadvantages": [],
    })


def test_the_slots_of_a_charged_multipower_share_its_charges_and_pay_no_end():
    """6E1 p.409: "the Multipower as a whole has as many Charges as are
    bought for the reserve; each slot does not have that many Charges ---
    all the slots, taken together, have that many Charges"; p.403: "the
    slots do not cost END". The slots had no Charges at all here, so they
    fired without limit, and paid full END."""
    from kirby_combat.charges import charge_pool

    hero = _rifle()
    slots = [p for p in hero.powers if p.xmlid == "ENERGYBLAST"]
    assert len(slots) == 2, [p.xmlid for p in hero.powers]
    reserve = slots[0].parent
    assert reserve.xmlid == "MULTIPOWER"
    assert {charge_pool(s) for s in slots} == {(str(reserve.id), 4)}
    from kirby_combat.hero_view import HeroCombatant

    attacks = HeroCombatant.from_build(hero, id="l").attacks
    assert {end_cost(a) for a in attacks if a.xmlid == "ENERGYBLAST"} == {0}


def _fired(who, source_id):
    import uuid
    from datetime import datetime, timezone

    from kirby_combat.session.events import ActionDeclared, ActionResolved, make_author_engine

    base = lambda: dict(id=str(uuid.uuid4()), session_id="s", sequence=1,  # noqa: E731
                        timestamp=datetime.now(timezone.utc), author=make_author_engine())
    d = ActionDeclared(**base(), combatant_id=who, action_type="attack", targets=["x"])
    r = ActionResolved(**base(), declaration_event_id=d.id,
                       result_payload={"kind": "attack", "power_source_id": source_id})
    return [d, r]


def _lazer_fight():
    from dataclasses import replace

    from kirby_combat.hero_view import HeroCombatant
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.side import Side
    from kirby_combat.synthetic import synthetic_combatant
    from kirby_combat.template import RAW_SUPERHEROIC

    lazer = replace(HeroCombatant.from_build(_rifle(), id="l"), side=Side.named("a"))
    other = synthetic_combatant(id="o", name="o", spd=3, side=Side.named("b"))
    return CombatSession.create(id="s", combatants=[lazer, other], scene=None,
                                template=RAW_SUPERHEROIC, dice_roller=None), lazer, other


def test_firing_either_slot_draws_on_the_one_supply():
    from kirby_combat.charges import spent_charges

    session, lazer, _ = _lazer_fight()
    s1, s2 = (a.source_id for a in lazer.attacks if a.xmlid == "ENERGYBLAST")
    reserve = lazer.attacks[0].charge_pool
    session = replace_log(session, [*_fired("l", s1), *_fired("l", s2), *_fired("l", s1)])
    assert spent_charges(session, "l") == {reserve: 3}


def test_when_the_supply_is_spent_neither_slot_is_offered():
    from kirby_combat.charges import spent_charges
    from kirby_combat.enumeration import enumerate_actions

    session, lazer, other = _lazer_fight()
    slots = [str(a.source_id) for a in lazer.attacks if a.xmlid == "ENERGYBLAST"]

    def blasts(spent):
        return [a for a in enumerate_actions(lazer, [other], spent_charges=spent)
                if a.kind == "attack" and any(s in a.action_id for s in slots)]

    three = replace_log(session, [*_fired("l", slots[0])] * 1 + _fired("l", slots[1])
                        + _fired("l", slots[0]))
    assert blasts(spent_charges(three, "l")), "one Charge left: both slots offered"
    four = replace_log(three, [*three.event_log, *_fired("l", slots[1])])
    assert blasts(spent_charges(four, "l")) == []


def replace_log(session, events):
    from dataclasses import replace

    return replace(session, event_log=list(events))
