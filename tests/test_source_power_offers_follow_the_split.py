"""Every offer read off a source power follows the split (6E1 p.404-406).

Mind Control, Mind Scan, Flash, Entangle, Mental Illusions, Telepathy, Aid,
Drain, Healing and Dispel are not damage-shaped, so their offers are built
by walking the build's powers rather than from `attacks`. They walked the
build AS BOUGHT: Bokor's Multipower opened with only his Ranged Killing
Attack on still offered two Flashes, two Mental Entangles, Aid, Drain and
Mind Control out of slots holding 0 points. 6E1 p.405: "Drain STR 6d6 ...
assigns 40 ... can only use 4d6"; a slot holding nothing is off.

One door now (`HeroCombatant.powers_at_split`): a slot holding nothing is
not offered, a slot holding part of its cost is offered (and resolved) at
the dice its points buy, read off kirby-cost's priced copy
(`levels_within`), never worked out here.

Bokor (corpus) carries a 41-point Multipower whose slots are all FIXED. For
the part-share cases a slot is made variable the way the loader marks one
(``ultra = False``), so the same purchase, its Advantages and its id, is
priced at a share.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from kirby_combat.enumeration import enumerate_actions
from kirby_combat.framework import allocation_for
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_cost.engine.allocation import levels_within
from kirby_dice import RandomRoller

from tests.corpus import require_authored

FRAMEWORK = "1674532452187"
RKA = "1674701239535"          # Digitalis dust, 37
DRAIN = "1686189167441"        # Stinging Nettle Powder, Drain 3d6+1, 41
EMBRACE = "1675817734177"      # The Embrace of Baron Samedi, Entangle, 39
AID = "1674684975814"          # Mountain Thunder Powder, Aid 3d6, 36
SCORPION = "1674684810701"     # Scorpion Pepper powder, Flash 5d6, 37
DUTURA = "1674535357546"       # Dutura Powder, Flash 3d6, 37
ZOMBI = "1674531412470"        # Zombi JuJu Powder, Mind Control 5d6, 37
GRAVEYARD = "1761428808738"    # Graveyard Dust, Entangle, 38
HEALING = "1674685486763"      # Healing Powder, 35

#: The kinds that come off a source-power walk, and Bokor's slots behind them.
WALKED = {
    "drain": {DRAIN}, "aid": {AID}, "flash": {SCORPION, DUTURA},
    "mind_control": {ZOMBI}, "mental_entangle": {EMBRACE, GRAVEYARD},
    "entangle": {EMBRACE, GRAVEYARD},
}


def _bokor(*variable: str) -> HeroCombatant:
    build = require_authored("Bokor")
    for p in build.powers:
        if str(p.id) in variable:
            p.ultra = False          # how the loader marks a variable slot
    return replace(HeroCombatant.from_build(build, id="bokor"),
                   side=Side.named("bokor"))


def _opened(hero: HeroCombatant, **points: int) -> HeroCombatant:
    split = {s.slot_id: 0 for f in hero.framework_view()
             if f.framework_id == FRAMEWORK for s in f.slots}
    split.update({k.removeprefix("s"): v for k, v in points.items()})
    return replace(hero, state=replace(hero.state, slot_points={FRAMEWORK: split}))


def _session(hero: HeroCombatant):
    foe = replace(HeroCombatant.from_build(require_authored("Ravel"), id="ravel"),
                  side=Side.named("ravel"))
    template = CombatTemplate.default_6e_superheroic()
    s = CombatSession.create(id="s", scene=None, template=template,
                             dice_roller=RandomRoller(seed=3),
                             combatants=[hero, foe]).start()
    return s, template


def _offers(hero: HeroCombatant):
    s, _ = _session(hero)
    actor = s.combatants[hero.id]
    return enumerate_actions(actor, [s.combatants["ravel"]],
                             slot_allocation=allocation_for(s, actor))


def _source_ids(offers, kind: str) -> set[str]:
    return {str(o._attack_view.id) for o in offers
            if o.kind == kind and o._attack_view is not None}


def _power(hero: HeroCombatant, slot_id: str):
    return next(p for p in hero._build().powers if str(p.id) == slot_id)


# ── a slot holding nothing is not offered ──────────────────────────────────

def test_opened_with_only_the_rka_on_offers_nothing_from_the_other_slots():
    offers = _offers(_opened(_bokor(), **{f"s{RKA}": 37}))
    for kind, slots in WALKED.items():
        assert not (_source_ids(offers, kind) & slots), kind
    assert not [o for o in offers if o.kind == "healing"]


@pytest.mark.parametrize("kind,slot,cost", [
    ("drain", DRAIN, 41), ("aid", AID, 36), ("flash", SCORPION, 37),
    ("mind_control", ZOMBI, 37), ("mental_entangle", GRAVEYARD, 38),
])
def test_a_slot_holding_its_cost_is_offered_and_the_rest_are_not(kind, slot, cost):
    offers = _offers(_opened(_bokor(), **{f"s{slot}": cost}))
    assert _source_ids(offers, kind) == {slot}
    for other, slots in WALKED.items():
        assert not (_source_ids(offers, other) & (slots - {slot})), other


def test_before_the_opening_the_build_reads_as_written():
    """Not opened: every slot as bought (setup only; a fight opens first)."""
    offers = _offers(_bokor())
    assert _source_ids(offers, "flash") == {SCORPION, DUTURA}
    assert _source_ids(offers, "mind_control") == {ZOMBI}


# ── a slot holding part of its cost fights at what its points buy ──────────

@pytest.mark.parametrize("kind,slot,points", [
    ("drain", DRAIN, 20), ("flash", SCORPION, 15),
    ("mind_control", ZOMBI, 20), ("mental_entangle", GRAVEYARD, 20),
    ("aid", AID, 20),
])
def test_a_part_share_is_offered_at_the_levels_its_points_buy(kind, slot, points):
    hero = _opened(_bokor(slot), **{f"s{slot}": points})
    want = levels_within(_power(hero, slot), points, hero=None).power
    assert want.levels < _power(hero, slot).levels        # really smaller
    views = [o._attack_view for o in _offers(hero) if o.kind == kind]
    assert views and all(str(v.id) == slot for v in views)
    assert {int(v.levels) for v in views} == {int(want.levels)}
    assert {int(round(v.active_cost)) for v in views} == {int(round(want.active_cost))}


def test_the_flash_offer_says_the_dice_its_share_buys():
    hero = _opened(_bokor(SCORPION), **{f"s{SCORPION}": 15})
    want = int(levels_within(_power(hero, SCORPION), 15, hero=None).power.levels)
    [offer] = [o for o in _offers(hero) if o.kind == "flash"]
    assert f"({want}d6 Flash BODY" in offer.summary


class _Spy(RandomRoller):
    def __init__(self, seed):
        super().__init__(seed=seed)
        self.counts: list[int] = []

    def roll_dice(self, count, sides=6):
        self.counts.append(count)
        return super().roll_dice(count, sides)


@pytest.mark.parametrize("kind,slot,points,full", [
    ("flash", SCORPION, 15, 5), ("mind_control", ZOMBI, 20, 5),
])
def test_seam_the_resolver_rolls_the_dice_the_share_buys(kind, slot, points, full):
    """offer -> resolve_chosen -> the dice actually rolled."""
    hero = _opened(_bokor(slot), **{f"s{slot}": points})
    want = int(levels_within(_power(hero, slot), points, hero=None).power.levels)
    assert want not in (full, 3)        # 3 is the to-hit roll's count
    s, template = _session(hero)
    actor = s.combatants[hero.id]
    offer = next(o for o in enumerate_actions(
        actor, [s.combatants["ravel"]], slot_allocation=allocation_for(s, actor))
        if o.kind == kind)
    hit = 0
    for seed in range(1, 40):        # until one lands, so the effect is rolled
        spy = _Spy(seed=seed)
        resolve_chosen(s, actor, offer, template=template, roller=spy)
        assert full not in spy.counts
        if want in spy.counts:
            hit += 1
    assert hit, "no seed reached the effect roll"


def test_seam_a_drain_resolves_at_the_dice_its_share_buys():
    hero = _opened(_bokor(DRAIN), **{f"s{DRAIN}": 20})
    priced = levels_within(_power(hero, DRAIN), 20, hero=None).power
    s, template = _session(hero)
    actor = s.combatants[hero.id]
    offer = next(o for o in enumerate_actions(
        actor, [s.combatants["ravel"]], slot_allocation=allocation_for(s, actor))
        if o.kind == "drain")
    assert int(offer._attack_view.levels) == int(priced.levels) < 3
    from kirby_combat.adjustments import effect_dice
    assert effect_dice(offer._attack_view) == effect_dice(priced)
    resolve_chosen(s, actor, offer, template=template, roller=RandomRoller(seed=5))


# ── a rebuilt combatant ────────────────────────────────────────────────────

def test_a_rebuilt_combatant_walks_no_powers_and_does_not_crash():
    """His stub build has no powers (a pre-existing gap: rebuilt, he is
    offered none of these), and the door answers [] rather than raising."""
    import json

    from kirby_combat.serialization import from_dict, to_dict

    live = _opened(_bokor(), **{f"s{ZOMBI}": 37})
    rebuilt = from_dict(json.loads(json.dumps(to_dict(live))))
    assert rebuilt.powers_at_split({"MINDCONTROL", "FLASH", "DRAIN"}) == []
    assert rebuilt.at_split(None) is None
