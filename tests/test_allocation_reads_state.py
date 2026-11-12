"""Every reader of a Multipower allocation reads the split folded onto the
combatant (`CombatantState.slot_points`), not the log.

6E1 p.402 (a slot that loses the reserve stops working), p.404-406 (the
split is points per slot; a slot holding none is off).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from kirby_combat import framework
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.framework import Allocation, allocation_for, slot_points_for
from kirby_combat.models import FrameworkView, SlotView
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import SlotsAllocated, make_author_engine
from kirby_combat.side import Side
from kirby_combat.upkeep import slot_on, slot_still_allocated
from kirby_dice import RandomRoller

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.template import CombatTemplate


def _view() -> FrameworkView:
    slots = [SlotView(slot_id=i, name=i, active_points=p, variable=True,
                      kind="attack", attack=None)
             for i, p in (("bolt", 40), ("wind", 40), ("wall", 40))]
    return FrameworkView(framework_id="kmp", xmlid="MULTIPOWER", name="MP",
                         kind="multipower", reserve_or_pool=60, slots=slots)


def _priced_view() -> FrameworkView:
    """`_view` with stand-in ladders: the menu's re-split offer reads the
    priced view (R10)."""
    from kirby_combat.hero_view import SlotEffect, SlotStep
    from kirby_combat.models import PricedSlotView

    return FrameworkView(
        framework_id="kmp", xmlid="MULTIPOWER", name="MP", kind="multipower",
        reserve_or_pool=60, slots=[PricedSlotView(
            slot_id=sl.slot_id, name=sl.name, active_points=sl.active_points,
            variable=True, kind="attack", attack=None,
            steps=tuple(SlotStep(p, f"{p} pts", SlotEffect.nothing())
                        for p in range(0, sl.active_points + 1, 10)))
            for sl in _view().slots])


def _session():
    def man(i, side):
        return synthetic_combatant(
            id=i, name=i, ocv=8, dcv=5, omcv=5, dmcv=5, spd=4, dex=20,
            ego=15, str_=15, con=18, pre=15, rec=6, pd=4, ed=4, rpd=2,
            red=2, md=3, power_defense=0, flash_defense=0, max_stun=40,
            max_body=12, max_end=40, current_stun=40, current_body=12,
            current_end=40, side=Side.named(side), attacks=[])
    s = CombatSession.create(
        id="s", scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
        combatants=[man("alice", "heroes"), man("bob", "villains")]).start()
    object.__setattr__(s.combatants["alice"], "framework_view", lambda: [_view()])
    return s


def _split(session, points, *, opening=True):
    session = apply_event(session, SlotsAllocated(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=datetime.now(UTC),
        author=make_author_engine(), combatant_id="alice",
        framework_id="kmp", slot_points=points, opening=opening))
    object.__setattr__(session.combatants["alice"], "framework_view", lambda: [_view()])
    return session


SPLIT = {"bolt": 40, "wind": 20, "wall": 0}


def test_allocation_is_assembled_from_the_folded_split():
    s = _split(_session(), SPLIT)
    got = allocation_for(s, s.combatants["alice"])["kmp"]
    assert isinstance(got, Allocation)
    assert got == Allocation(60, 60, {"bolt", "wind"},
                             {"bolt": 40, "wind": 40, "wall": 40}, SPLIT)
    # indexes 0-3 keep their meaning for existing callers
    assert got[0] == 60 and got[1] == 60 and got[2] == {"bolt", "wind"}


def test_slot_points_for_is_none_before_the_opening():
    s = _session()
    assert slot_points_for(s.combatants["alice"], "kmp") is None
    assert allocation_for(s, s.combatants["alice"]) == {}
    assert slot_points_for(_split(s, SPLIT).combatants["alice"], "kmp") == SPLIT


def test_active_slots_is_gone():
    assert not hasattr(framework, "active_slots")


def test_slot_on_is_points_above_zero():
    s = _split(_session(), SPLIT)
    alice = s.combatants["alice"]
    alloc = allocation_for(s, alice)
    on = lambda sid: slot_on(alice, type("P", (), {"id": sid})(), alloc)  # noqa: E731
    assert on("bolt") and on("wind")
    assert not on("wall")


def test_a_slot_cut_to_nothing_is_no_longer_allocated():
    s = _split(_session(), SPLIT)
    power = type("P", (), {"id": "wall", "framework_id": "kmp", "slot_id": "wall"})()
    assert not slot_still_allocated(s, "alice", power)
    power.slot_id = "bolt"
    assert slot_still_allocated(s, "alice", power)
    # before the opening: the build as written
    assert slot_still_allocated(_session(), "alice", power)


def test_a_zero_point_slot_is_not_usable_in_enumeration():
    """The gate is 'holds points', not 'fits the remainder': a 20-point
    share of a 40-point slot is usable."""
    from kirby_combat.models import AttackPower

    def blast(sid):
        return AttackPower(
            xmlid="ENERGYBLAST", name="Blast", damage_dice=4, half_die=False,
            plus_one=False, damage_type="normal", defense_type="ed",
            range_m=60.0, uses_str=False, str_min=0, armor_piercing=0,
            penetrating=0, increased_stun_mult=0, framework_xmlid="MULTIPOWER",
            framework_id="kmp", slot_id=sid)

    s = _split(_session(), SPLIT)
    alice, bob = s.combatants["alice"], s.combatants["bob"]
    cls = type("A", (type(alice),), {"attacks": property(
        lambda self: [blast("bolt"), blast("wind"), blast("wall")])})
    alice = cls(id=alice.id, hero=alice.hero, state=alice.state,
                knockback_resistance=alice.knockback_resistance)
    object.__setattr__(alice, "framework_view", lambda: [_view()])
    object.__setattr__(alice, "priced_framework_view", lambda: [_priced_view()])
    offers = enumerate_actions(alice, [bob],
                               slot_allocation=allocation_for(s, alice))
    used = {a.action_id for a in offers if a.kind == "attack"}
    assert any("bolt" in i for i in used) and any("wind" in i for i in used)
    assert not any("wall" in i for i in used)
