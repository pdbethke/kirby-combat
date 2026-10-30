"""Endurance Reserves: END batteries (6E1 p.207-208).

61 of 989 corpus characters own one --- a suit's power packs, a flamethrower's
fuel tank --- and combat had never read it: every power paid from the
character's own END, the Reserve's END and REC were never consulted, and a
man whose blasts ran off a battery tired himself out instead.

THE RULES, quoted (6E1 p.207):
- "A character with an Endurance Reserve must decide which powers draw
  energy from the Reserve, and which draw energy from his personal END. A
  power can normally only draw energy from one or the other." HD records
  the choice per power (USE_END_RESERVE).
- "If an Endurance Reserve doesn't function for any reason, a character can
  draw no END from it. That means he can't use any power that draws END
  only from the Endurance Reserve ... A character cannot spend STUN in the
  place of Endurance Reserve END."
- "An Endurance Reserve normally Recovers its REC in END each Turn ... during
  every Post-Segment 12 Recovery", "even if the character is Knocked Out".
  "You can decrease this return rate with a Limitation" (6E1 p.208: Extra
  Time, Limited Recovery).
- "If a character has two or more Endurance Reserves that could supply END
  to the same power, the character can choose whichever one he wants."
  RULING: he draws on the fullest.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from kirby_cost.io.build_json import build_from_json
from kirby_dice import FakeRoller, RandomRoller

from kirby_combat.encounter import Encounter
from kirby_combat.endurance import reserve_end
from kirby_combat.enumeration import LegalAction
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import RAW_HEROIC
from tests.corpus import require_template


@pytest.fixture(autouse=True)
def _a_template():
    """kirby-cost prices a build only against a HERO Designer template,
    which neither it nor CI ships."""
    require_template()


def _reserve(levels=40, rec=10, rec_modifiers=(), rid="R"):
    return {"id": rid, "xmlid": "ENDURANCERESERVE", "levels": levels,
            "endurance_reserve_rec": {"xmlid": "ENDURANCERESERVEREC",
                                      "levels": rec,
                                      "modifiers": list(rec_modifiers)}}


def _doc(powers):
    return {
        "name": "Battery", "template": "Main6E",
        "base_points": 400, "disad_points": 75, "experience": 0,
        # Every characteristic at its base: the build is seeded only with
        # what it lists, and a man needs END and STUN to fight.
        "characteristics": [{"xmlid": x, "levels": 0} for x in (
            "STR", "DEX", "CON", "INT", "EGO", "PRE", "OCV", "DCV", "OMCV",
            "DMCV", "SPD", "PD", "ED", "REC", "END", "BODY", "STUN")],
        "powers": powers,
        "skills": [], "perks": [], "talents": [], "disadvantages": [],
    }


_SUIT = [
    _reserve(),
    # 8d6, 40 Active Points: 4 END, from the Reserve.
    {"id": "PB", "xmlid": "ENERGYBLAST", "levels": 8, "input": "ED",
     "name": "Power Blast", "use_end_reserve": True},
    # 6d6, 30 Active Points: 3 END, his own.
    {"id": "HB", "xmlid": "ENERGYBLAST", "levels": 6, "input": "ED",
     "name": "Hand Blast"},
]


def _man(cid, powers, side):
    hero = build_from_json(_doc(powers))
    return replace(HeroCombatant.from_build(hero, id=cid), side=Side.named(side))


def _session(powers=_SUIT, template=RAW_HEROIC, scene=None):
    return CombatSession.create(
        id="s", combatants=[_man("suit", powers, "a"), _man("mook", [], "b")],
        scene=scene, template=template, dice_roller=FakeRoller([]),
    ).start()


def _blast(session, name):
    power = next(p for p in session.combatants["suit"].attacks if p.name == name)
    return LegalAction(action_id=f"attack:mook:{name}", kind="attack",
                       target_id="mook", power_xmlid=power.xmlid,
                       power_name=power.name, summary=name, _attack_view=power)


def _fire(session, name, template=RAW_HEROIC):
    """The dice do not matter here: END is paid hit or miss."""
    return resolve_chosen(session, session.combatants["suit"], _blast(session, name),
                          template=template, roller=RandomRoller(seed=1))


# ---------------------------------------------------------------------------
# Read off the build
# ---------------------------------------------------------------------------

def test_his_reserve_and_which_powers_draw_on_it():
    suit = _session().combatants["suit"]
    [r] = suit.reserves()
    assert r.id, "spent by its own id"
    assert (r.max_end, r.rec, r.recovers_every_turns) == (40, 10, 1)
    draws = {p.name: p.uses_end_reserve for p in suit.attacks}
    assert draws == {"Power Blast": True, "Hand Blast": False}


def test_extra_time_on_the_rec_slows_it():
    """Blowtorch's fuel tank: REC with Extra Time (1 Day). A Day is 7,200
    Turns of 12 seconds: never in a fight."""
    suit = _man("suit", [_reserve(rec_modifiers=[
        {"xmlid": "EXTRATIME", "option_id": "1DAY"}])], "a")
    assert suit.reserves()[0].recovers_every_turns == 7200


def test_limited_recovery_never_recovers_in_a_fight():
    """RULING on 6E1 p.208's "only when plugged into an electrical socket"."""
    suit = _man("suit", [_reserve(rec_modifiers=[
        {"xmlid": "LIMITEDRECOVERY", "option_id": "", "levels": 0}])], "a")
    assert suit.reserves()[0].recovers_every_turns is None


# ---------------------------------------------------------------------------
# Paying
# ---------------------------------------------------------------------------

def _reserve_rows(resolved):
    """(storage of the Reserve, change, why) --- by storage, because the
    loader gives each Reserve its own id."""
    size = {r.id: r.max_end
            for r in resolved.session.combatants["suit"].reserves()}
    return [(size[e.reserve_id], e.end, e.reason) for e in resolved.events
            if e.kind == "EnduranceReserveChanged"]


def test_a_reserve_power_is_paid_from_the_reserve_not_from_him():
    session = _session()
    before = session.combatants["suit"].state.current_end
    out = _fire(session, "Power Blast")
    assert _reserve_rows(out) == [(40, -4, "end_spent")]
    assert out.session.combatants["suit"].state.current_end == before
    [r] = out.session.combatants["suit"].reserves()
    assert reserve_end(out.session, "suit", r) == 36


def test_his_own_power_is_paid_from_his_own_end():
    session = _session()
    before = session.combatants["suit"].state.current_end
    out = _fire(session, "Hand Blast")
    assert _reserve_rows(out) == []
    assert out.session.combatants["suit"].state.current_end == before - 3


def test_an_empty_battery_runs_nothing():
    """3 END left in a Reserve cannot pay for a 4 END blast, and he may not
    pay for it with STUN or his own END: the blast is not offered. His own
    blast still is."""
    from kirby_combat.loop.run import _situation_for

    session = _session(powers=[_reserve(levels=3)] + _SUIT[1:])
    names = {a.power_name for a in _situation_for(session, "suit").menu
             if a.kind == "attack"}
    assert "Hand Blast" in names
    assert "Power Blast" not in names


def test_a_campaign_that_does_not_count_end_spends_none_of_it():
    off = replace(RAW_HEROIC, manage_endurance=False, manage_endurance_npc=False)
    session = _session(template=off)
    assert _reserve_rows(_fire(session, "Power Blast", template=off)) == []


def test_he_draws_on_the_fullest_of_two():
    """RULING on 6E1 p.207's "can choose whichever one he wants"."""
    session = _session(powers=[_reserve(levels=10, rid="small"),
                               _reserve(levels=50, rid="big")] + _SUIT[1:])
    assert _reserve_rows(_fire(session, "Power Blast")) == [(50, -4, "end_spent")]


# ---------------------------------------------------------------------------
# Recovering
# ---------------------------------------------------------------------------

def _through_segment_12(session):
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session],
                    template=session.template)
    return enc.advance_segment().sessions[0]


def test_the_reserve_recovers_its_rec_after_segment_12_up_to_its_storage():
    session = _fire(_session(), "Power Blast").session       # 36 of 40
    after = _through_segment_12(session)
    [r] = after.combatants["suit"].reserves()
    assert reserve_end(after, "suit", r) == 40, "10 REC, but only 4 of room"
    rows = [(e.end, e.reason) for e in after.event_log
            if e.kind == "EnduranceReserveChanged"]
    assert rows[-1] == (4, "recovery")


def test_it_recovers_while_he_is_out_cold():
    session = _fire(_session(), "Power Blast").session
    suit = session.combatants["suit"]
    session = replace(session, combatants={
        **session.combatants,
        "suit": replace(suit, state=replace(suit.state, current_stun=-5))})
    after = _through_segment_12(session)
    [r] = after.combatants["suit"].reserves()
    assert reserve_end(after, "suit", r) == 40


def test_a_tank_that_refills_once_a_day_does_not_refill_in_a_fight():
    session = _session(powers=[_reserve(rec_modifiers=[
        {"xmlid": "EXTRATIME", "option_id": "1DAY"}])] + _SUIT[1:])
    after = _through_segment_12(_fire(session, "Power Blast").session)
    [r] = after.combatants["suit"].reserves()
    assert reserve_end(after, "suit", r) == 36


def test_flight_off_the_battery_is_paid_from_the_battery():
    """Defender's suit runs "Blast, Flight ... and so on" off its Reserve
    (6E1 p.207). Flight 20m costs 2 END a full move (6E1 p.158)."""
    from kirby_world.scene import (
        AmbientConditions, Position, Scene, SceneBounds, Surface,
    )

    powers = [_reserve(),
              {"id": "FL", "xmlid": "FLIGHT", "levels": 20, "use_end_reserve": True}]
    scene = Scene(
        id="lot", name="lot", bounds=SceneBounds(0, 0, 0, 100, 100, 50),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(0, 0), (100, 0), (100, 100), (0, 100)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(gravity_scale=1.0),
        combatant_positions={"suit": Position(0, 10, 0), "mook": Position(60, 10, 0)},
    )
    session = _session(powers=powers, scene=scene)
    before = session.combatants["suit"].state.current_end
    move = LegalAction(action_id="move:flight:mook", kind="move", target_id="mook",
                       power_xmlid=None, power_name=None, mode="flight",
                       summary="fly at him")
    out = resolve_chosen(session, session.combatants["suit"], move,
                         template=RAW_HEROIC, roller=RandomRoller(seed=1))
    assert _reserve_rows(out) == [(40, -2, "end_spent")]
    assert out.session.combatants["suit"].state.current_end == before
