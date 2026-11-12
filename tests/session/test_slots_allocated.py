"""A Multipower split is an event, folded onto the combatant (6E1 p.404-406).

`SlotsAllocated.slot_points` is ABSOLUTE and names every slot of the
framework (0 = off): folding replaces that framework's entry whole, and
leaves the combatant's other frameworks alone. Data path only: what a
split may be is decided elsewhere.
"""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.serialization.from_dict import from_dict
from kirby_combat.serialization.to_dict import to_dict
from kirby_combat.session import CombatSession, apply_event
from kirby_combat.session.events import SlotsAllocated, make_author_engine
from kirby_combat.template import CombatTemplate
from kirby_dice import FakeRoller


def _session() -> CombatSession:
    c = synthetic_combatant(
        id="alice", name="alice", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    return CombatSession.create(
        id="s1", combatants=[c], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def _allocate(s, framework, points, who="alice", opening=False):
    return apply_event(s, SlotsAllocated(
        id=f"e{len(s.event_log) + 1}", session_id=s.id,
        sequence=len(s.event_log) + 1, timestamp=datetime.now(timezone.utc),
        author=make_author_engine(), combatant_id=who, framework_id=framework,
        slot_points=points, opening=opening))


def test_event_shape():
    s = _session()
    e = SlotsAllocated(
        id="e1", session_id="s1", sequence=1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id="alice", framework_id="mp1",
        slot_points={"a": 30, "b": 0}, opening=True)
    assert e.kind == "SlotsAllocated" and e.opening is True


def test_a_combatant_starts_with_no_split():
    assert _session().combatants["alice"].state.slot_points == {}


def test_applying_sets_the_framework_entry():
    s = _allocate(_session(), "mp1", {"a": 30, "b": 10, "c": 0}, opening=True)
    assert s.combatants["alice"].state.slot_points == {
        "mp1": {"a": 30, "b": 10, "c": 0}}


def test_a_second_allocation_replaces_the_framework_whole():
    s = _allocate(_session(), "mp1", {"a": 30, "b": 10, "c": 0})
    s = _allocate(s, "mp1", {"a": 0, "b": 0, "c": 40})
    assert s.combatants["alice"].state.slot_points == {
        "mp1": {"a": 0, "b": 0, "c": 40}}


def test_two_frameworks_on_one_combatant_stay_independent():
    s = _allocate(_session(), "mp1", {"a": 30, "b": 10})
    s = _allocate(s, "vpp1", {"x": 25})
    s = _allocate(s, "mp1", {"a": 0, "b": 40})
    assert s.combatants["alice"].state.slot_points == {
        "mp1": {"a": 0, "b": 40}, "vpp1": {"x": 25}}


def test_the_fold_does_not_alias_the_events_dict():
    pts = {"a": 30}
    s = _allocate(_session(), "mp1", pts)
    pts["a"] = 99
    assert s.combatants["alice"].state.slot_points["mp1"] == {"a": 30}


def test_an_unknown_combatant_raises():
    with pytest.raises(ValueError, match="ghost"):
        _allocate(_session(), "mp1", {"a": 1}, who="ghost")


def test_slot_points_round_trip_through_the_wire():
    s = _allocate(_session(), "mp1", {"a": 30, "b": 0})
    s = _allocate(s, "vpp1", {"x": 25})
    wire = to_dict(s.combatants["alice"])
    assert wire["slot_points"] == {"mp1": {"a": 30, "b": 0}, "vpp1": {"x": 25}}
    back = from_dict(wire)
    assert back.state.slot_points == s.combatants["alice"].state.slot_points


def test_a_pre_split_dict_raises_and_says_why():
    wire = to_dict(_session().combatants["alice"])
    del wire["slot_points"]
    wire["active_slot_per_framework"] = {}
    with pytest.raises(ValueError, match="slot_points.*active_slot_per_framework"):
        from_dict(wire)


def test_a_dict_without_slot_points_raises():
    wire = to_dict(_session().combatants["alice"])
    del wire["slot_points"]
    with pytest.raises(ValueError, match="slot_points"):
        from_dict(wire)
