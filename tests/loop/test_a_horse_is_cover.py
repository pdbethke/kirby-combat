"""A standing horse is cover (`kirby_combat.bodies`), like a wagon its size.

6E2 p.45 Behind Cover; the record has Tom McLaury behind a horse. RULING
(Peter, 2026-11-27): a standing neutral body shelters a man from shooters on
its far side, and when it bolts or falls the cover goes with it.

The horse here is built from this file's own words, not the Bestiary's sheet.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from shaped import scene_with, session_on
from tests.conftest_grips import _CHARS, gun
from kirby_combat.actions.recording import _cover_against
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.models import AttackInput, DiceValues
from kirby_combat.side import Side
from kirby_combat.template import RAW_SUPERHEROIC

LAW, COW = Side.named("law"), Side.named("cow")
HORSES = Side.named("horses", neutral=True)
LARGE = "Large (4m; +2 OCV for others to hit)"


@pytest.fixture(autouse=True)
def _template_needed():
    from tests.corpus import require_template
    require_template()


def _built(id_, side, *, large=False, guns=()):
    from kirby_cost.io.build_json import build_from_json

    hero = build_from_json({
        "name": id_, "template": "builtIn.Heroic6E.hdt", "base_points": 100,
        "disad_points": 0, "experience": 0, "characteristics": _CHARS,
        "powers": list(guns), "skills": [], "perks": [], "talents": [],
        "martial_arts": [], "equipment": [],
        "disadvantages": ([{"id": "l", "xmlid": "PHYSICALLIMITATION", "base_cost": 0.0,
                            "alias": "Physical Complication", "input": LARGE}] if large else [])})
    return replace(HeroCombatant.from_build(hero, id=id_), side=side)


def _cover(horse_at, *, horse_side=HORSES):
    shooter = _built("shooter", LAW, guns=[gun("g", "Gun")])
    tom, horse = _built("tom", COW), _built("horse", horse_side, large=True)
    positions = {"shooter": (0, 0, 0), "tom": (4, 0, 0), "horse": horse_at}
    session = session_on(scene_with(positions), shooter, tom, horse, template=RAW_SUPERHEROIC)
    attack = AttackInput(attacker=session.combatants["shooter"], target=session.combatants["tom"],
                         power=session.combatants["shooter"].attacks[0], distance_m=4,
                         aim=None, dice=DiceValues())
    return _cover_against(session, attack, RAW_SUPERHEROIC)[0], session


def test_a_horse_between_them_is_cover():
    assert _cover((2.5, 0, 0))[0] == 2


def test_a_horse_off_to_the_side_is_not():
    assert _cover((2.5, 4, 0))[0] == 0


def test_a_man_is_not_a_horse():
    """Only a neutral Large body shelters: a fighter in the way is not cover."""
    assert _cover((2.5, 0, 0), horse_side=COW)[0] == 0


def test_a_shot_beside_the_horse_spooks_it_and_the_cover_goes():
    """Western Hero p.113 and the ruling: his PRE Roll, Timid (Strong) -5.
    A 13 fails: it bolts, and Tom is in the open."""
    from kirby_combat.actions.recording import resolve_attack_in_session
    from kirby_combat.bodies import sheltering_bodies
    from kirby_combat.nerve import FLED, nerve_state
    from kirby_dice import FakeRoller

    timid = {"id": "t", "xmlid": "PSYCHOLOGICALLIMITATION", "base_cost": 0.0,
             "alias": "Psychological Complication", "input": "Timid",
             "adders": [{"xmlid": "SITUATION", "option_id": "COMMON", "base_cost": 10.0,
                         "selected": True, "required": True, "include_in_base": True},
                        {"xmlid": "INTENSITY", "option_id": "STRONG", "base_cost": 5.0,
                         "selected": True, "required": True, "include_in_base": True}]}
    from kirby_cost.io.build_json import build_from_json
    horse_hero = build_from_json({
        "name": "horse", "template": "builtIn.Heroic6E.hdt", "base_points": 100,
        "disad_points": 0, "experience": 0, "characteristics": _CHARS,
        "powers": [], "skills": [], "perks": [], "talents": [], "martial_arts": [],
        "equipment": [], "disadvantages": [
            {"id": "l", "xmlid": "PHYSICALLIMITATION", "base_cost": 0.0,
             "alias": "Physical Complication", "input": LARGE}, timid]})
    horse = replace(HeroCombatant.from_build(horse_hero, id="horse"), side=HORSES)
    shooter = _built("shooter", LAW, guns=[gun("g", "Gun")])
    tom = _built("tom", COW)
    session = session_on(scene_with({"shooter": (0, 0, 0), "tom": (4, 0, 0),
                                     "horse": (4, 1.5, 0)}),
                         shooter, tom, horse, template=RAW_SUPERHEROIC)
    attack = AttackInput(attacker=session.combatants["shooter"], target=session.combatants["tom"],
                         power=session.combatants["shooter"].attacks[0], distance_m=4,
                         aim=None, dice=DiceValues(to_hit=[6, 6, 6]))
    session, _ = resolve_attack_in_session(session, attack, RAW_SUPERHEROIC,
                                           roller=FakeRoller([[6, 6, 1]]))
    from kirby_combat.wounds import characteristic_roll_of

    rolled = [e for e in session.event_log if e.kind == "NerveRolled"][0]
    pre = characteristic_roll_of(session.combatants["horse"], "PRE")
    assert rolled.modifiers == ("Timid:-5",)
    assert (rolled.needed, rolled.outcome) == (pre - 5, FLED)
    assert nerve_state(session, "horse") == FLED
    assert sheltering_bodies(session) == []


def test_a_bolted_horse_runs_from_the_fight():
    """A horse that has spooked breaks off like a man who ran (`nerve`):
    its menu is Disengage and nothing else. It has no enemies (neutral), so
    it runs from everyone still fighting. A model-seat run, seed 0, 2026-11-28:
    with no Disengage on offer, both horses were handed the defensive menu
    and chose "hide" eleven times without ever leaving the lot."""
    import uuid
    from datetime import datetime, timezone

    from kirby_combat.loop.run import _situation_for
    from kirby_combat.nerve import FLED
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import NerveRolled, make_author_engine

    shooter = _built("shooter", LAW, guns=[gun("g", "Gun")])
    tom, horse = _built("tom", COW), _built("horse", HORSES, large=True)
    session = session_on(scene_with({"shooter": (0, 0, 0), "tom": (4, 0, 0),
                                     "horse": (4, 1.5, 0)}),
                         shooter, tom, horse, template=RAW_SUPERHEROIC)
    session = apply_event(session, NerveRolled(
        id=str(uuid.uuid4()), session_id=session.id, sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id="horse", roll=18, needed=7, modifiers=(), outcome=FLED))
    menu = _situation_for(session, "horse").menu
    assert [a.kind for a in menu] == ["disengage"], [a.kind for a in menu]
