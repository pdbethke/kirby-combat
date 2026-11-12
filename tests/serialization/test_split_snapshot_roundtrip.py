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
    return [s for f in c.priced_framework_view() if f.framework_id == FRAMEWORK
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


def test_points_between_two_rungs_read_the_lower_rung():
    """6E1 p.406: points need not sit on a step; the highest rung that fits."""
    live = _kerendor()
    rebuilt = _rebuilt(live)
    off = _all_off(live)
    checked = 0
    for slot in _variable_slots(live):
        pts = [st.points for st in slot.steps]
        for lo, hi in zip(pts, pts[1:]):
            if hi - lo > 1 and hi - lo != slot.active_points:
                _assert_same(live, rebuilt, {**off, slot.slot_id: lo + 1})
                checked += 1
    assert checked


def test_recording_while_a_split_is_in_force_records_the_build_not_the_split():
    live = _kerendor()
    off = _all_off(live)
    held = _with_split(live, {**off, RP: 9, FLIGHT: 20, PD_SLOT: 8})
    rebuilt = _rebuilt(held)
    assert rebuilt.state.slot_points == held.state.slot_points
    assert _views(held) == _views(rebuilt)                 # the split in force
    _assert_same(held, rebuilt, {**off, RP: 45, TELE: 12})  # and a different one


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


# ── the plain framework_view prices nothing ─────────────────────────────────
def test_the_plain_framework_view_prices_no_ladder(monkeypatch):
    live = _kerendor()

    def boom(*a, **k):
        raise AssertionError("framework_view priced a ladder")
    monkeypatch.setattr(HeroCombatant, "_slot_steps", boom)
    views = live.framework_view()
    assert views and not any(hasattr(sl, "steps")
                             for f in views for sl in f.slots)


def test_a_ladder_is_priced_once_per_build():
    import kirby_cost.engine.allocation as allocation
    live = _kerendor()
    real, calls = allocation.ladder, []
    allocation.ladder = lambda p: (calls.append(1), real(p))[1]
    try:
        live.priced_framework_view()
        first = len(calls)
        live.priced_framework_view()
        again = replace(live, state=replace(live.state, current_stun=1))
        again.priced_framework_view()
    finally:
        allocation.ladder = real
    assert first and len(calls) == first


def test_a_priced_slot_view_must_state_its_steps():
    from kirby_combat.models import PricedSlotView
    with pytest.raises(TypeError):
        PricedSlotView(slot_id="a", name="a", active_points=1, variable=True,
                       kind="other")


def test_the_rebuilt_plain_view_equals_the_live_plain_view():
    live = _kerendor()
    assert _rebuilt(live).framework_view() == live.framework_view()


# ── a share of a slot with no step between off and as bought (R9) ───────────
def _offer(live):
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.framework import split_choice_of
    [view] = [f for f in live.priced_framework_view() if f.framework_id == FRAMEWORK]
    choice = split_choice_of(view, {}, presets=())
    return LegalAction(
        action_id=f"reallocate_slots:{FRAMEWORK}:split", kind="reallocate",
        target_id=None, power_xmlid=None, power_name=None, summary="split",
        choice=choice)


def test_the_split_check_refuses_a_part_share_of_an_unladderable_slot():
    from kirby_combat.loop.chooser import InvalidChoice, validate_choice
    live = _kerendor()
    offer = _offer(live)
    [dr] = [s for s in _variable_slots(live) if s.slot_id == DR]
    base = offer.action_id
    with pytest.raises(InvalidChoice, match="Kerendor DR"):
        validate_choice(f"{base}={DR}@1", [offer])
    for ok in (0, dr.active_points):
        validate_choice(f"{base}={DR}@{ok}+{RP}@9" if ok else f"{base}={RP}@9",
                        [offer])


def test_the_resolver_refuses_a_part_share_of_an_unladderable_slot():
    from kirby_combat.encounter import Encounter  # noqa: F401
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.side import Side
    from kirby_combat.template import CombatTemplate
    from kirby_dice import RandomRoller
    from fixtures.synthetic_hero import synthetic_combatant

    live = replace(_kerendor(), side=Side.named("blue"))
    foe = synthetic_combatant(id="foe", name="foe", side=Side.named("red"))
    session = CombatSession.create(
        id="s", scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1), combatants=[live, foe]).start()
    act = lambda tail: LegalAction(   # noqa: E731
        action_id=f"opening_split:{FRAMEWORK}:split={tail}", kind="opening_split",
        target_id=None, power_xmlid=None, power_name=None, summary="")
    kw = dict(template=CombatTemplate.default_6e_superheroic(),
              roller=RandomRoller(seed=1))
    me = session.combatants[live.id]
    with pytest.raises(UnresolvableAction):
        resolve_chosen(session, me, act(f"{DR}@1"), **kw)
    resolve_chosen(session, me, act(f"{RP}@9"), **kw)


def test_a_rebuilt_combatant_raises_on_a_part_share_of_an_unladderable_slot():
    live = _kerendor()
    rebuilt = _rebuilt(live)
    bad = _with_split(rebuilt, {**_all_off(rebuilt), DR: 1})
    with pytest.raises(ValueError, match="Kerendor DR"):
        bad.defense_view()
