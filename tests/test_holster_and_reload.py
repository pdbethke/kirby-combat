"""Draw, holster, drop (`holster`), and change Clips (`reload`).

6E1 p.76: drawing is a Half Phase, a Zero Phase with Fast Draw; a Fast Draw
roll changes Clips as a Half Phase. 6E1 p.371: changing Clips is a Full
Phase; a power whose Charges have no Clips holds one and cannot reload in
the fight. Rulings (Peter, 2026-11-27): dropping is a Zero Phase Action,
holstering a Half Phase like drawing, Fast Draw needs no roll to draw, and
a holstered weapon is stated in the grips.

Doc Holliday is the case: two shots in a two-handed shotgun, his Colt in its
holster, and until this nothing let him reach it.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from kirby_dice import FakeRoller

from tests.conftest_grips import gun, gunman, session_of, weapon_id
from kirby_combat.action_time import ActionTime, time_of
from kirby_combat.charges import clips_on, spent_charges
from kirby_combat.grips import BOTH, HOLSTERED, RIGHT, Grip, grip_of, state_grips
from kirby_combat.holster import DRAW, DROP, hand_offers
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.reload import RELOAD, reload_offers
from kirby_combat.template import RAW_HEROIC

import kirby_combat.loop  # noqa: F401  (registers the resolvers)

SIX = {"xmlid": "CHARGES", "option_id": "SIX", "base_cost": -0.75}
SIX_IN_TWO_CLIPS = {**SIX, "adders": [{"xmlid": "CLIPS", "levels": 1, "base_cost": 0.0,
                                       "selected": True}]}


@pytest.fixture(autouse=True)
def _template_needed():
    from tests.corpus import require_template
    require_template()


def _doc():
    shotgun = gun("sg", "Shotgun", two_handed=True)
    colt = gun("colt", "Colt")
    doc = gunman("doc", shotgun, colt)
    session = session_of(doc, template=RAW_HEROIC)
    return state_grips(session, "doc", [Grip(weapon_id(doc, "Shotgun"), BOTH),
                                        Grip(weapon_id(doc, "Colt"), HOLSTERED)])


def _offer(session, kind):
    return next(o for o in hand_offers(session, session.combatants["doc"]) if o.kind == kind)


def _do(session, offer, rolls=()):
    return resolve_chosen(session, session.combatants[offer.action_id and "doc"], offer,
                          template=RAW_HEROIC, roller=FakeRoller(list(rolls))).session


def test_a_holstered_gun_is_off_his_sheet():
    session = _doc()
    assert [a.name for a in session.combatants["doc"].attacks] == ["Shotgun"]


def test_with_both_hands_full_he_cannot_draw():
    session = _doc()
    assert not [o for o in hand_offers(session, session.combatants["doc"]) if o.kind == DRAW]


def test_drop_the_shotgun_then_draw_the_colt():
    session = _doc()
    drop = [o for o in hand_offers(session, session.combatants["doc"])
            if o.kind == DROP and o.power_name == "Shotgun"][0]
    assert time_of(drop) is ActionTime.ZERO
    session = _do(session, drop)
    doc = session.combatants["doc"]
    assert grip_of(session, "doc", weapon_id(doc, "Shotgun")) is None
    draw = _offer(session, DRAW)
    assert draw.power_name == "Colt" and time_of(draw) is ActionTime.HALF
    session = _do(session, draw)
    assert grip_of(session, "doc", weapon_id(session.combatants["doc"], "Colt")) == RIGHT
    assert [a.name for a in session.combatants["doc"].attacks] == ["Colt"]


def test_fast_draw_draws_in_no_time(monkeypatch):
    """6E1 p.76; ruling: no roll."""
    import kirby_combat.holster as holster

    session = _doc()
    session = _do(session, [o for o in hand_offers(session, session.combatants["doc"])
                            if o.kind == DROP][0])
    monkeypatch.setattr(holster, "has_fast_draw", lambda actor: True)
    offer = _offer(session, holster.FAST_DRAW)
    assert time_of(offer) is ActionTime.ZERO


def _rifleman(charges):
    rifle = {**gun("r", "Rifle"), "modifiers": [{"xmlid": "FOCUS", "option_id": "OAF",
                                                  "base_cost": -1.0}, charges]}
    man = gunman("doc", rifle)
    return session_of(man, template=RAW_HEROIC), man


def _spend(session, man, shots):
    """Fire it ``shots`` times through the attack door, every shot a 3."""
    from kirby_combat.actions.recording import resolve_attack_in_session
    from kirby_combat.models import AttackInput, DiceValues
    from fixtures.synthetic_hero import synthetic_combatant

    from kirby_combat.side import Side
    target = synthetic_combatant(id="t", name="T", spd=2, side=Side.named("b"))
    session = replace(session, combatants={**session.combatants, "t": target})
    for _ in range(shots):
        attack = AttackInput(attacker=session.combatants["doc"], target=session.combatants["t"],
                             power=session.combatants["doc"].attacks[0], distance_m=2,
                             aim=None, dice=DiceValues(to_hit=[1, 1, 1], damage=[1, 1]))
        session, _ = resolve_attack_in_session(session, attack, RAW_HEROIC,
                                               roller=FakeRoller([[6, 6]] * 4))
    return session


def test_clips_are_read_off_the_build():
    assert clips_on(_rifleman(SIX_IN_TWO_CLIPS)[1].hero.powers[0]) == 2
    assert clips_on(_rifleman(SIX)[1].hero.powers[0]) == 1


def test_plain_charges_cannot_reload_in_the_fight():
    session, man = _rifleman(SIX)
    session = _spend(session, man, 2)
    assert reload_offers(session, session.combatants["doc"]) == []


def test_a_fresh_clip_is_a_full_phase_and_restarts_the_count():
    session, man = _rifleman(SIX_IN_TWO_CLIPS)
    session = _spend(session, man, 3)
    pool = str(man.hero.powers[0].id)
    assert spent_charges(session, "doc")[pool] == 3
    offer = next(o for o in reload_offers(session, session.combatants["doc"]) if o.kind == RELOAD)
    assert time_of(offer) is ActionTime.FULL
    session = resolve_chosen(session, session.combatants["doc"], offer,
                             template=RAW_HEROIC, roller=FakeRoller([])).session
    assert spent_charges(session, "doc")[pool] == 0
    session = _spend(session, man, 1)
    assert reload_offers(session, session.combatants["doc"]) == [], "no spare clip left"


def test_doctrine_drops_the_empty_shotgun_and_draws():
    """Seam: `rearm` through `TacticChooser`, on the menu the loop builds.
    A two-shot shotgun and an enemy to shoot: he shoots while it is loaded,
    and once both shots are gone he lets it fall (no time) to draw."""
    import uuid
    from datetime import datetime, timezone

    from fixtures.synthetic_hero import synthetic_combatant
    from kirby_combat.loop.chooser import TacticChooser
    from kirby_combat.loop.run import _situation_for
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ChargeSpent, make_author_engine
    from kirby_combat.side import Side
    from tests.conftest_grips import TWO_HANDS, OAF

    two_shots = {"xmlid": "CHARGES", "option_id": "TWO", "base_cost": -1.5}
    shotgun = {**gun("sg", "Shotgun"), "modifiers": [OAF, TWO_HANDS, two_shots]}
    doc = gunman("doc", shotgun, gun("colt", "Colt"))
    foe = synthetic_combatant(id="foe", name="Foe", spd=2, side=Side.named("b"))
    session = session_of(doc, foe, template=RAW_HEROIC)
    session = state_grips(session, "doc", [Grip(weapon_id(doc, "Shotgun"), BOTH),
                                           Grip(weapon_id(doc, "Colt"), HOLSTERED)])
    loaded = TacticChooser().choose(_situation_for(session, "doc"))
    assert not loaded.startswith("drop_weapon"), loaded

    pool = str(next(p for p in doc.hero.powers if p.name == "Shotgun").id)
    for _ in range(2):
        session = apply_event(session, ChargeSpent(
            id=str(uuid.uuid4()), session_id=session.id, sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc), author=make_author_engine(),
            combatant_id="doc", power_source_id=pool))
    empty = TacticChooser().choose(_situation_for(session, "doc"))
    assert empty.startswith("drop_weapon:"), empty


def test_a_fast_draw_reload_is_a_half_phase_on_a_made_roll(monkeypatch):
    """6E1 p.76: "a successful Fast Draw roll also allows him to change Clips
    as a Half Phase Action"; a miss takes the Full Phase (6E1 p.371)."""
    import kirby_combat.holster as holster
    from kirby_combat.action_time import rolled_time
    from kirby_combat.reload import FAST_RELOAD

    monkeypatch.setattr(holster, "has_fast_draw", lambda actor: True)
    for roll, took in (([1, 1, 2], ActionTime.HALF), ([6, 6, 6], ActionTime.FULL)):
        session, man = _rifleman(SIX_IN_TWO_CLIPS)
        session = _spend(session, man, 1)
        doc = session.combatants["doc"]
        monkeypatch.setattr(type(doc), "skill_roll_value",
                            lambda self, x: 12 if x == "FASTDRAW" else None, raising=False)
        offer = next(o for o in reload_offers(session, doc) if o.kind == FAST_RELOAD)
        assert time_of(offer) is ActionTime.ROLLED
        resolved = resolve_chosen(session, doc, offer, template=RAW_HEROIC,
                                  roller=FakeRoller([roll]))
        assert rolled_time(resolved) is took
        assert spent_charges(resolved.session, "doc")[str(man.hero.powers[0].id)] == 0


def test_a_fast_draw_holster_takes_no_time(monkeypatch):
    import kirby_combat.holster as holster

    session = _doc()
    session = _do(session, [o for o in hand_offers(session, session.combatants["doc"])
                            if o.kind == DROP][0])
    session = _do(session, _offer(session, DRAW))
    monkeypatch.setattr(holster, "has_fast_draw", lambda actor: True)
    offer = _offer(session, holster.FAST_HOLSTER)
    assert time_of(offer) is ActionTime.ZERO
    session = _do(session, offer)
    assert grip_of(session, "doc", weapon_id(session.combatants["doc"], "Colt")) == HOLSTERED
