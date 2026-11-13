"""A characteristic bought in a Multipower slot adds what its split holds.

6E1 p.404-406: a variable slot holds the points its split gave it and has as
many levels as fit them; a fixed slot is its full Active Points or nothing; a
slot holding none is off. A +30 STR slot is a characteristic like any other
purchase, so at 15 points it is +15 STR (priced by kirby-cost's
`levels_within`, never worked out here), at 30 it is +30, and at 0 nothing.

HD marks such a slot AFFECTS_TOTAL="No" (a slot is not always in play), and
kirby-cost reads the build as written by that flag, so BEFORE a framework is
opened it adds nothing: Ravel's STR is 10 and Power Lad's 40, as they were
before splits existed. Once a split says how much the slot holds, that is the
situation the flag stood for (`characteristic_states(slots=...)`).

Ravel's "Reinforced String" is a variable +30 STR slot (30 Active Points);
Power Lad's "Just Like the Old Days..." a fixed +45 STR slot (45).
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from kirby_combat.hero_view import HeroCombatant
from kirby_combat.serialization import from_dict, to_dict
from kirby_cost.engine.allocation import levels_within

from tests.corpus import require_authored

RAVEL_FW = "1648348957819"
STRING = "1648356198397"
LAD_FW = "1727271632187"
OLD_DAYS = "1727272554833"


def _hero(name: str) -> HeroCombatant:
    return HeroCombatant.from_build(require_authored(name))


def _split(hero: HeroCombatant, fw: str, **points: int) -> HeroCombatant:
    full = {s.slot_id: 0 for f in hero.framework_view()
            if f.framework_id == fw for s in f.slots}
    full.update({k.removeprefix("s"): v for k, v in points.items()})
    return replace(hero, state=replace(hero.state, slot_points={fw: full}))


def _string_levels(hero: HeroCombatant, points: int) -> int:
    power = next(p for p in hero._build().powers if str(p.id) == STRING)
    return int(levels_within(power, points, hero=None).power.levels)


def test_before_the_opening_the_build_reads_as_written():
    assert _hero("Ravel").combat_stats().str_ == 10
    assert _hero("PowerLad").combat_stats().str_ == 40


@pytest.mark.parametrize("points", [0, 15, 30])
def test_ravels_string_adds_what_its_split_holds(points):
    ravel = _hero("Ravel")
    got = _split(ravel, RAVEL_FW, **{f"s{STRING}": points}).combat_stats().str_
    want = 10 + (_string_levels(ravel, points) if points else 0)
    assert got == want
    assert got == {0: 10, 15: 25, 30: 40}[points]      # the book's arithmetic


def test_a_fixed_characteristic_slot_is_all_or_nothing():
    lad = _hero("PowerLad")
    assert _split(lad, LAD_FW).combat_stats().str_ == 40
    assert _split(lad, LAD_FW, **{f"s{OLD_DAYS}": 45}).combat_stats().str_ == 85



def _rebuilt(live: HeroCombatant) -> HeroCombatant:
    return from_dict(json.loads(json.dumps(to_dict(live))))


@pytest.mark.parametrize("points", [0, 15, 30])
def test_a_rebuilt_ravel_reads_the_same_str_at_each_split(points):
    live = _hero("Ravel")
    rebuilt = _rebuilt(live)
    split = {f"s{STRING}": points}
    assert (_split(rebuilt, RAVEL_FW, **split).combat_stats().str_
            == _split(live, RAVEL_FW, **split).combat_stats().str_)


def test_a_rebuilt_ravel_recorded_after_the_opening_reads_the_same():
    """Recorded mid-fight with the string on: the snapshot holds the build
    as written, and the split rides on the state."""
    live = _split(_hero("Ravel"), RAVEL_FW, **{f"s{STRING}": 15})
    assert _rebuilt(live).combat_stats().str_ == live.combat_stats().str_ == 25


def test_a_rebuilt_power_lad_reads_the_same_str_on_and_off():
    live = _hero("PowerLad")
    rebuilt = _rebuilt(live)
    for split in ({}, {f"s{OLD_DAYS}": 45}):
        assert (_split(rebuilt, LAD_FW, **split).combat_stats().str_
                == _split(live, LAD_FW, **split).combat_stats().str_)
