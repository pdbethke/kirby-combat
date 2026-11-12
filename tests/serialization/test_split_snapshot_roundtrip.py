"""A combatant rebuilt from a snapshot splits his reserve as the live one did.

6E1 p.404-406: a variable slot holds the points its split gave it and has as
many levels as fit them. The snapshot cannot carry the build, so it records
each slot's PRICED LADDER (kirby-cost's `ladder`; nothing is priced here) and
a rebuilt combatant picks the highest step that fits the points allocated.
That is the answer `levels_within` gives, read from the recording.

For Ravel's variable attack slot and for the synthetic Kerendor build the
defence/movement tests use, every step of every variable slot is tried: live
-> JSON -> rebuilt, the same `state.slot_points` set on both, and every view
the split moves must agree.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from kirby_combat.hero_view import HeroCombatant
from kirby_combat.serialization import from_dict, to_dict

from tests.corpus import require_authored
from tests.test_defences_and_movement_follow_the_split import (
    DN, DR, FIXED_FLIGHT, FLIGHT, FRAMEWORK, NAKED, PD_SLOT, POWD, RP, TELE,
    _kerendor,
)

ARMAMENTS = "1648351359965"


def _ravel() -> HeroCombatant:
    return HeroCombatant.from_build(require_authored("Ravel"))


def _rebuilt(live: HeroCombatant) -> HeroCombatant:
    return from_dict(json.loads(json.dumps(to_dict(live))))


def _with_split(c: HeroCombatant, split: dict[str, int]) -> HeroCombatant:
    return replace(c, state=replace(c.state, slot_points={FRAMEWORK: dict(split)}))


def _all_off(c: HeroCombatant) -> dict[str, int]:
    return {s.slot_id: 0 for f in c.framework_view()
            if f.framework_id == FRAMEWORK for s in f.slots}


def _views(c: HeroCombatant):
    return (c.attacks, c.defense_view(), c.movement_view(), c.combat_stats())


def _variable_slots(c: HeroCombatant):
    return [s for f in c.framework_view() if f.framework_id == FRAMEWORK
            for s in f.slots if s.variable]


def _assert_same(live: HeroCombatant, rebuilt: HeroCombatant, split: dict[str, int]):
    a, b = _with_split(live, split), _with_split(rebuilt, split)
    for name, x, y in zip(("attacks", "defense_view", "movement_view", "combat_stats"),
                          _views(a), _views(b)):
        assert x == y, f"{name} differs at split {split}"


@pytest.mark.parametrize("make", [_ravel, _kerendor], ids=["ravel", "kerendor"])
def test_every_step_of_every_variable_slot_rebuilds_the_same(make):
    live = make()
    rebuilt = _rebuilt(live)
    off = _all_off(live)
    slots = _variable_slots(live)
    assert slots
    tried = 0
    for slot in slots:
        assert slot.steps, f"{slot.name} recorded no ladder"
        for step in slot.steps:
            _assert_same(live, rebuilt, {**off, slot.slot_id: step.points})
            tried += 1
    assert tried > len(slots)           # more than the 0 step each


@pytest.mark.parametrize("make", [_ravel, _kerendor], ids=["ravel", "kerendor"])
def test_the_framework_not_yet_opened_rebuilds_as_bought(make):
    live = make()
    rebuilt = _rebuilt(live)
    assert _views(live) == _views(rebuilt)


def test_the_split_moves_the_rebuilt_views_not_just_equals_them():
    """Negative control: the ladder is really read, not the full recording."""
    live = _kerendor()
    rebuilt = _rebuilt(live)
    off = _all_off(live)
    def rp(c, points):
        return [d for d in _with_split(c, {**off, RP: points}).defense_view()
                if d.name == "Kerendor RP"]
    assert rp(rebuilt, 45) != rp(rebuilt, 9) and rp(rebuilt, 9)
    assert rp(rebuilt, 0) == []


def test_several_slots_at_once_and_a_fixed_slot_rebuild_the_same():
    live = _kerendor()
    rebuilt = _rebuilt(live)
    off = _all_off(live)
    _assert_same(live, rebuilt, {
        **off, RP: 9, FLIGHT: 20, TELE: 12, PD_SLOT: 8, NAKED: 1, POWD: 8,
        FIXED_FLIGHT: 25, DR: 30,
    })
    _assert_same(live, rebuilt, {**off, FIXED_FLIGHT: 25})


def test_an_unladderable_slot_records_exactly_nothing_and_full():
    """6E1 p.404-406 cannot split what has no levels: kirby-cost raises
    `NotLadderable`, and the snapshot records the two steps that exist."""
    live = _kerendor()
    for sid in (DR, DN):
        [slot] = [s for s in _variable_slots(live) if s.slot_id == sid]
        assert [st.points for st in slot.steps] == [0, slot.active_points]


def test_a_drained_combatant_with_a_split_rebuilds_the_same():
    live = _kerendor()
    live = replace(live, state=replace(live.state, drains={"pd": 2}))
    rebuilt = _rebuilt(live)
    off = _all_off(live)
    _assert_same(live, rebuilt, {**off, PD_SLOT: 20, RP: 45})


def test_a_snapshot_whose_slots_carry_no_ladder_is_refused():
    """Old fights are disposable: it says why and offers no way round."""
    payload = json.loads(json.dumps(to_dict(_kerendor())))
    for fw in payload["frameworks"]:
        for slot in fw["slots"]:
            slot.pop("steps")
    with pytest.raises(ValueError, match="steps"):
        from_dict(payload)


def test_re_recording_a_rebuilt_combatant_keeps_the_ladders():
    live = _kerendor()
    again = _rebuilt(_rebuilt(live))
    off = _all_off(live)
    _assert_same(live, again, {**off, RP: 9, FLIGHT: 20})
