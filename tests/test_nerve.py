"""Nerve: the PRE Roll when a man's side is breaking (`kirby_combat.nerve`).

Western Hero p.128: "you might make a PRE roll for a person facing
overwhelming odds to resist fleeing"; 6E2 p.139: he "may surrender, run
away, or faint". Rulings (Peter, 2026-11-27) in the module docstring.

The side here is three men, one of them down: a third of it, SHAKEN
(`morale._CASUALTY_TIERS`). PRE 10 rolls 11-.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from kirby_dice import FakeRoller

from tests.corpus import require_template
from fixtures.terms import terms_stated
from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.nerve import (
    FLED, HELD, SURRENDERED, modifiers, nerve_check, nerve_state,
)
from kirby_combat.roster import Roster
from kirby_combat.session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import RAW_HEROIC

US, THEM = Side.named("us"), Side.named("them")
#: Every characteristic at its base (PRE 10, BODY 10, STUN 20...): a build
#: doc with none states none, and he would arrive at 0 STUN, already down.
_CHARS = [{"xmlid": x, "levels": 0} for x in (
    "STR", "DEX", "CON", "BODY", "STUN", "END", "SPD", "PD", "ED", "REC", "OCV",
    "DCV", "PRE", "EGO", "INT")]


@pytest.fixture(autouse=True)
def _template_needed():
    require_template()


def _psych(text, intensity="MODERATE"):
    return {"id": f"d-{text}", "xmlid": "PSYCHOLOGICALLIMITATION", "base_cost": 0.0,
            "min_cost": 0.0, "alias": "Psychological Complication", "input": text,
            "adders": [{"xmlid": "SITUATION", "option_id": "COMMON", "base_cost": 10.0,
                        "selected": True, "required": True, "include_in_base": True},
                       {"xmlid": "INTENSITY", "option_id": intensity, "base_cost": 5.0,
                        "selected": True, "required": True, "include_in_base": True}]}


def _man(id_, *complications, armed=True, side=US):
    from kirby_cost.io.build_json import build_from_json

    gun = {"id": "g", "xmlid": "RKA", "name": "Revolver", "levels": 2, "input": "PD",
           "modifiers": [{"xmlid": "FOCUS", "option_id": "OAF", "base_cost": -1.0}]}
    hero = build_from_json({
        "name": id_, "template": "builtIn.Heroic6E.hdt", "base_points": 175,
        "disad_points": 50, "experience": 0, "characteristics": _CHARS,
        "powers": [gun] if armed else [], "skills": [], "perks": [], "talents": [],
        "martial_arts": [], "equipment": [], "disadvantages": list(complications)})
    return replace(HeroCombatant.from_build(hero, id=id_), side=side)


def _fight(man, *, shaken=True):
    down = synthetic_combatant(id="down", name="Down", spd=2, max_stun=20,
                               max_body=10, current_body=0 if shaken else 10,
                               side=US)
    friend = synthetic_combatant(id="friend", name="Friend", spd=2, side=US)
    foe = synthetic_combatant(id="foe", name="Foe", spd=3, side=THEM)
    return terms_stated(CombatSession.create(
        id="s", combatants=[man, down, friend, foe], scene=None,
        template=RAW_HEROIC, dice_roller=FakeRoller([])).start())


def _rolled(session):
    return [e for e in session.event_log if e.kind == "NerveRolled"]


def test_a_steady_side_does_not_roll():
    session = nerve_check(_fight(_man("m"), shaken=False), "m", roller=FakeRoller([]))
    assert _rolled(session) == []


def test_a_made_pre_roll_holds():
    session = nerve_check(_fight(_man("m")), "m", roller=FakeRoller([[3, 3, 4]]))  # 10 vs 11-
    assert _rolled(session)[0].outcome == HELD
    assert nerve_state(session, "m") is None


def test_a_failed_roll_runs_when_he_can():
    session = nerve_check(_fight(_man("m")), "m", roller=FakeRoller([[6, 6, 1]]))  # 13
    assert _rolled(session)[0].outcome == FLED and nerve_state(session, "m") == FLED


def test_fearless_never_rolls():
    session = nerve_check(_fight(_man("m", _psych("Vengeful"))), "m", roller=FakeRoller([]))
    assert _rolled(session) == []


def test_the_penalties():
    """Not Brave (Moderate) -3, unarmed -2."""
    man = _man("m", _psych("Not Brave"), armed=False)
    assert dict(modifiers(_fight(man), man)) == {"Not Brave": -3, "unarmed": -2}
    strong = _man("m", _psych("Coward", "STRONG"))
    assert dict(modifiers(_fight(strong), strong)) == {"Coward": -5}
    needed = _rolled(nerve_check(_fight(man), "m", roller=FakeRoller([[1, 2, 2]])))[0].needed
    assert needed == 11 - 3 - 2


def test_a_cornered_man_surrenders_and_is_out_of_the_fight(monkeypatch):
    import kirby_combat.nerve as nerve

    monkeypatch.setattr(nerve, "can_flee", lambda session, cid: False)
    session = nerve_check(_fight(_man("m")), "m", roller=FakeRoller([[6, 6, 6]]))
    assert nerve_state(session, "m") == SURRENDERED
    roster = Roster(session)
    assert "m" not in roster.standing.get(US, [])
    assert "m" not in [c.id for c in roster.enemies_of(session.combatants["foe"])]


def test_through_the_loop_a_surrendered_man_spends_his_phase_on_nothing(monkeypatch):
    """Seam: `run_phase` rolls the check at the top of his Phase."""
    import kirby_combat.nerve as nerve
    from kirby_combat.encounter import Encounter
    from kirby_combat.loop.run import run_phase
    from kirby_combat.squads import KEEP_ORDERS

    monkeypatch.setattr(nerve, "can_flee", lambda session, cid: False)
    session = _fight(_man("m"))
    encounter = Encounter(id="e", turn=1, segment=11, sessions=[session],
                          template=RAW_HEROIC).run_segment(roller=lambda: [3, 3, 3])

    class _Any:
        def give_orders(self, page):
            return KEEP_ORDERS

        def choose(self, situation):
            return situation.menu[0].action_id

    class _Sixes:
        """Every die a 6: the PRE Roll is an 18, which always fails (6E1
        p.57), and every shot misses, so nothing else changes the side."""

        def roll_dice(self, count, sides):
            return [6] * count

    dice = _Sixes()
    for _ in range(12):
        encounter = run_phase(encounter, _Any(), roller=dice, on_unresolvable="skip").encounter
        s = encounter.sessions[0]
        if any(e.kind == "PhaseSpent" and e.combatant_id == "m" for e in s.event_log):
            break
    spent = [e for e in s.event_log if e.kind == "PhaseSpent" and e.combatant_id == "m"]
    assert spent and spent[0].reason == "surrendered", spent


def test_a_man_who_ran_is_offered_no_attack():
    """Seam: the loop narrows his menu to breaking off (`nerve.flee_menu`);
    with no map there is nowhere to break off to, so only what keeps him
    alive is left."""
    from kirby_combat.loop.run import _situation_for

    session = nerve_check(_fight(_man("m")), "m", roller=FakeRoller([[6, 6, 6]]))
    assert nerve_state(session, "m") == FLED
    kinds = {a.kind for a in _situation_for(session, "m").menu}
    assert kinds and not kinds & {"attack", "strike", "multiple_attack", "haymaker"}, kinds
