"""An attack from a Multipower slot fights at the points its split gave it.

6E1 p.404-406: a variable slot may hold fewer points than it was bought at,
and then has as many levels as fit them; a slot holding none is off. 6E1
p.129-130: Endurance is paid on the Active Points actually used.

The character is the corpus's Ravel, whose "ARMaments" slot is a variable
Hand-To-Hand Attack bought at 45 Active Points. Every expected number is
read off the priced copy kirby-cost returns (`levels_within`), never worked
out here: this module does no cost arithmetic of its own.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from kirby_combat.enumeration import enumerate_actions
from kirby_combat.framework import allocation_for
from kirby_combat.hero_view import HeroCombatant, _build_attack_power
from kirby_cost.engine.allocation import NotLadderable, levels_within

from tests.corpus import require_authored

ARMAMENTS = "1648351359965"          # variable HTH slot, 45 AP
FIXED_ATTACK = "1648350992201"       # "String Storm": fixed attack slot, 45 AP
FRAMEWORK = "1648348957819"


def _ravel() -> HeroCombatant:
    return HeroCombatant.from_build(require_authored("Ravel"))


def _split(hero: HeroCombatant, **points: int) -> HeroCombatant:
    """Ravel after a SlotsAllocated: ARMaments (and any named slot) at the
    given points, every other slot off."""
    full = {s.slot_id: 0 for f in hero.framework_view()
            if f.framework_id == FRAMEWORK for s in f.slots}
    full.update({k.removeprefix("s"): v for k, v in points.items()})
    state = replace(hero.state, slot_points={FRAMEWORK: full})
    return replace(hero, state=state)


def _power(hero: HeroCombatant, slot_id: str):
    return next(p for p in hero._build().powers if str(p.id) == slot_id)


def _armaments(hero: HeroCombatant):
    return [a for a in hero.attacks if a.slot_id == ARMAMENTS]


def _expected(hero: HeroCombatant, points: int):
    """The attack view built from the priced copy, the way the engine must."""
    fit = levels_within(_power(hero, ARMAMENTS), points)
    return _build_attack_power(
        fit.power, str_for_augmentation=hero.combat_stats().str_)


def test_the_build_as_written_before_the_opening_is_unchanged():
    hero = _ravel()
    [a] = _armaments(hero)
    assert a.active_points == 45
    assert a.damage_dice == _expected(hero, 45).damage_dice


def test_a_variable_slot_below_its_cost_fights_at_the_points_given():
    hero = _split(_ravel(), s1648351359965=40)
    [a] = _armaments(hero)
    want = _expected(hero, 40)
    full = _expected(hero, 45)
    assert want.damage_dice < full.damage_dice        # it really is smaller
    assert a.damage_dice == want.damage_dice
    assert a.half_die == want.half_die and a.plus_one == want.plus_one
    assert a.active_points == want.active_points == 40


def test_endurance_is_paid_on_the_points_used():
    hero = _split(_ravel(), s1648351359965=30)
    [a] = _armaments(hero)
    assert a.end_per_use == _expected(hero, 30).end_per_use
    assert a.end_per_use < _expected(hero, 45).end_per_use


def test_identity_is_the_originals_so_offers_and_adjustment_still_match():
    whole = _armaments(_ravel())[0]
    cut = _armaments(_split(_ravel(), s1648351359965=40))[0]
    assert (cut.slot_id, cut.source_id, cut.framework_id, cut.name) == (
        whole.slot_id, whole.source_id, whole.framework_id, whole.name)


def test_a_slot_holding_no_points_is_not_an_attack():
    hero = _split(_ravel(), s1648351359965=0)
    assert _armaments(hero) == []
    assert _armaments(replace(hero, state=replace(hero.state, slot_points={}))) != []


def test_the_menu_offers_no_attack_from_a_slot_holding_nothing():
    foe = HeroCombatant.from_build(require_authored("Bokor"))
    hero = _split(_ravel(), s1648351359965=0)
    offers = enumerate_actions(hero, [foe], slot_allocation=allocation_for(None, hero))
    assert not [o for o in offers if o.kind == "attack" and ARMAMENTS in o.action_id]


def test_an_offer_carries_the_attack_at_its_split():
    foe = HeroCombatant.from_build(require_authored("Bokor"))
    hero = _split(_ravel(), s1648351359965=40)
    offers = enumerate_actions(hero, [foe], slot_allocation=allocation_for(None, hero))
    mine = [o for o in offers if o.kind == "attack" and ARMAMENTS in o.action_id]
    assert mine
    assert {o._attack_view.damage_dice for o in mine} == {_expected(hero, 40).damage_dice}


def test_aid_lands_on_the_allocated_power():
    hero = _split(_ravel(), s1648351359965=40)
    base = _armaments(hero)[0].damage_dice
    aided = replace(hero, state=replace(
        hero.state, adjusted_dice={ARMAMENTS: 2}))
    assert _armaments(aided)[0].damage_dice == base + 2
    assert [a for a in aided.unadjusted_attacks() if a.slot_id == ARMAMENTS][0
            ].damage_dice == base


def test_a_fixed_slot_fights_as_bought():
    whole = {a.slot_id: a for a in _ravel().attacks}
    assert FIXED_ATTACK in whole
    cut = _split(_ravel(), **{f"s{FIXED_ATTACK}": 45})
    got = {a.slot_id: a for a in cut.attacks}
    assert got[FIXED_ATTACK] == whole[FIXED_ATTACK]
    assert ARMAMENTS not in got                       # the others are off


def test_a_slot_at_or_over_its_cost_fights_whole():
    hero = _split(_ravel(), s1648351359965=45)
    assert _armaments(hero) == _armaments(_ravel())


def test_the_slot_stays_an_attack_slot_in_the_framework_view_at_zero():
    """The view of the slot is as bought: a re-split from 0 must still see
    it as an attack slot."""
    hero = _split(_ravel(), s1648351359965=0)
    slot = next(s for f in hero.framework_view() for s in f.slots
                if s.slot_id == ARMAMENTS)
    assert slot.kind == "attack" and slot.active_points == 45


def test_the_original_power_is_never_touched():
    hero = _split(_ravel(), s1648351359965=30)
    p = _power(hero, ARMAMENTS)
    before = (p.levels, p.active_cost)
    hero.attacks
    assert (p.levels, p.active_cost) == before


def test_a_power_with_no_steps_raises_rather_than_fighting_at_full():
    import kirby_cost.engine.allocation as alloc

    def boom(power, points):
        raise NotLadderable("flat cost")
    hero = _split(_ravel(), s1648351359965=30)
    orig = alloc.levels_within
    alloc.levels_within = boom
    try:
        with pytest.raises(NotLadderable):
            hero.attacks
    finally:
        alloc.levels_within = orig


def test_seam_the_damage_roll_uses_the_allocated_dice():
    """offer -> resolve_chosen -> the dice actually rolled."""
    from kirby_combat.loop.registry import resolve_chosen
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.side import Side
    from kirby_combat.template import CombatTemplate
    from kirby_dice import RandomRoller

    class Spy(RandomRoller):
        def __init__(self, seed):
            super().__init__(seed=seed)
            self.counts: list[int] = []

        def roll_dice(self, count, sides=6):
            self.counts.append(count)
            return super().roll_dice(count, sides)

    hero = _split(_ravel(), s1648351359965=40)
    hero = replace(hero, side=Side.named("heroes")) if hasattr(hero, "side") else hero
    foe = HeroCombatant.from_build(require_authored("Bokor"))
    template = CombatTemplate.default_6e_superheroic()
    s = CombatSession.create(
        id="s", scene=None, template=template, dice_roller=RandomRoller(seed=3),
        combatants=[hero, foe]).start()
    actor = s.combatants[hero.id]
    enemy = s.combatants[foe.id]
    offers = enumerate_actions(actor, [enemy], slot_allocation=allocation_for(s, actor))
    offer = next(o for o in offers if o.kind == "attack" and ARMAMENTS in o.action_id)
    want = _expected(hero, 40).damage_dice
    assert want != _expected(hero, 45).damage_dice
    spy = Spy(seed=11)
    resolve_chosen(s, actor, offer, template=template, roller=spy)
    # a hit rolls the damage dice (+1 for a half die / stun multiplier on
    # killing); a miss rolls only the 3d6 to-hit, but the attack dice are
    # drawn up front (`_attack_dice`), so the count is there either way.
    assert want in spy.counts
    assert _expected(hero, 45).damage_dice not in spy.counts
