"""`HeroCombatant.movement_outside(framework_id)`: his movement with every
slot of that framework left out, whatever its split.

A seat weighing a Multipower split asks "can he close WITHOUT the split's
help?" (6E1 p.404-406: a slot's movement is the split's to give or take).
Before the opening `movement_view` reads every slot as bought; this reads
none of that framework's, opened or not, live or rebuilt from a snapshot.
"""
from __future__ import annotations

import json

import pytest

from kirby_combat.serialization import from_dict, to_dict

from tests.test_defences_and_movement_follow_the_split import (
    FLIGHT, FRAMEWORK, TELE, _kerendor, _split,
)


def _modes(caps):
    return sorted((m.mode, m.combat_m) for m in caps)


def _all_off(hero):
    return _split(hero)        # every slot of the Multipower at 0


def test_before_the_opening_his_slots_movement_is_left_out():
    hero = _kerendor()
    assert ("flight", 60.0) in _modes(hero.movement_view())  # read as bought
    assert _modes(hero.movement_outside(FRAMEWORK)) == _modes(
        _all_off(hero).movement_view())
    assert "flight" not in {m.mode for m in hero.movement_outside(FRAMEWORK)
                            if m.combat_m == 60.0}


def test_after_the_opening_whatever_the_split_it_is_left_out():
    hero = _split(_kerendor(), **{f"s{FLIGHT}": 60, f"s{TELE}": 0})
    assert ("flight", 60.0) in _modes(hero.movement_view())
    assert _modes(hero.movement_outside(FRAMEWORK)) == _modes(
        _all_off(hero).movement_view())


def test_a_rebuilt_combatant_answers_the_same():
    live = _kerendor()
    rebuilt = from_dict(json.loads(json.dumps(to_dict(live))))
    for hero in (live, _split(live, **{f"s{FLIGHT}": 60})):
        twin = rebuilt if hero is live else _split(rebuilt, **{f"s{FLIGHT}": 60})
        assert _modes(twin.movement_outside(FRAMEWORK)) == _modes(
            hero.movement_outside(FRAMEWORK))


def test_a_framework_he_does_not_have_is_refused():
    with pytest.raises(KeyError):
        _kerendor().movement_outside("no-such-framework")
