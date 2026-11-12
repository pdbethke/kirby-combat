"""The menu: one re-split offer per Multipower, with neutral presets.

6E1 p.404-406: a Multipower's reserve is divided among its slots, a fixed
slot whole or not at all, a variable one in any share up to its Active
Points; p.410: re-dividing it is a Zero Phase Action, once a Phase. A
variable share is unbounded, so the menu makes ONE offer per Multipower
(`SplitChoice`) that a seat completes with the points, and a short list of
presets a person at the table can read: the player's own standing splits
first, then "All in <slot>", "Even" and "<fixed slot> + remainder". None of
them reads the board.

Kerendor's Magical Powers (6E1 p.406): reserve 60; Lightning Bolt, Blast
12d6, variable; Wind Riding, Flight 60m, variable; Wall of Wind, Resistant
Protection 15 PD/15 ED, fixed (45). Built on the corpus's Ravel (his own
Multipower emptied and refilled) so every effect is priced by kirby-cost.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from tests.loop.conftest import encounter_of, fighter
from kirby_combat.encounter import Encounter
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.framework import StandingSplit
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop import run_phase
from kirby_combat.side import Side
from kirby_combat.squads import KEEP_ORDERS
from kirby_cost.services.power_builder import build_power_from_spec
from kirby_dice import RandomRoller

from tests.corpus import require_authored

FRAMEWORK = "1648348957819"            # Ravel's Multipower, refilled
OFFER = f"reallocate_slots:{FRAMEWORK}:split"
BOLT_ONLY = {"bolt": 60, "wind": 0, "wall": 0}


def _slot(spec: dict, slot_id: str, name: str, *, variable: bool = True):
    power, _active, _real = build_power_from_spec(spec)
    power._id = slot_id
    power.name = name
    power.ultra = not variable           # how the loader marks a Fixed slot
    if "levels" in spec:
        power.levels = int(spec["levels"])   # the loader's ints, not floats
    return power


def _kerendor(split=None, standing=()) -> HeroCombatant:
    build = require_authored("Ravel")
    framework = next(p for p in build.powers if str(p.id) == FRAMEWORK)
    build.powers = [p for p in build.powers
                    if getattr(p, "parent", None) is not framework]
    framework.name = "Magical Powers"
    framework.base_cost = 60
    for power in (
        _slot({"xmlid": "ENERGYBLAST", "levels": 12}, "bolt", "Lightning Bolt"),
        _slot({"xmlid": "FLIGHT", "levels": 60}, "wind", "Wind Riding"),
        _slot({"xmlid": "FORCEFIELD", "pd_levels": 15, "ed_levels": 15},
              "wall", "Wall of Wind", variable=False),
    ):
        power.parent = framework
        build.powers.append(power)
    hero = HeroCombatant.from_build(build, id="kerendor")
    return replace(hero, side=Side.named("heroes"), state=replace(
        hero.state,
        slot_points={FRAMEWORK: dict(split if split is not None else BOLT_ONLY)},
        standing_splits={FRAMEWORK: tuple(standing)}))


def _foe():
    return fighter("foe", side=Side.named("villains"))


def _splits(actor):
    return [a for a in enumerate_actions(actor, [_foe()]) if a.kind == "reallocate"]


# ── the offer ──────────────────────────────────────────────────────────────

def test_one_offer_per_multipower_named_in_words():
    [offer] = _splits(_kerendor())
    assert offer.action_id == OFFER
    assert offer.summary == "Re-split Magical Powers (60 reserve): now Blast 12d6"
    assert offer.choice is not None and offer.choice.current == BOLT_ONLY


def test_a_split_with_nothing_on_says_so():
    [offer] = _splits(_kerendor({"bolt": 0, "wind": 0, "wall": 0}))
    assert offer.summary.endswith("now nothing switched on")


def test_the_offer_carries_each_slots_ladder():
    [offer] = _splits(_kerendor())
    terms = {t.slot_id: t for t in offer.choice.slots}
    assert terms["bolt"].steps[:3] == (0, 5, 10)
    assert terms["wall"].steps == (0, 45)
    assert not terms["wall"].variable


def test_the_presets_are_neutral_and_in_order():
    [offer] = _splits(_kerendor())
    got = [(p.name, p.effect_text, p.standing) for p in offer.choice.presets]
    assert got == [
        # All in Lightning Bolt is the split in force: dropped.
        ("All in Wind Riding", "Flight 60m", False),
        ("Even", "Blast 6d6, Flight 30m", False),
        # 15 left after the Wall goes to the Bolt first, in slot order.
        ("Wall of Wind + remainder",
         "Resistant Protection 15 PD/15 ED, Blast 3d6", False),
    ]
    assert offer.choice.presets[2].points == {"bolt": 15, "wind": 0, "wall": 45}


def test_every_preset_is_an_answer_the_offer_accepts():
    from kirby_combat.loop.chooser import validate_choice

    [offer] = _splits(_kerendor())
    for preset in offer.choice.presets:
        done = validate_choice(offer.action_id + offer.choice.answer(preset.points),
                               [offer])
        assert done.action_id.startswith(OFFER + "=")


def test_not_offered_before_the_framework_is_opened():
    """The opening is part of setting up the fight (Task 11), not a re-split."""
    hero = _kerendor()
    hero = replace(hero, state=replace(hero.state, slot_points={}))
    assert _splits(hero) == []


def test_an_armed_man_with_enemies_up_may_still_put_it_all_into_flight():
    """The "don't disarm him" guard is not the split offer's (spec §5.3):
    everything into Flight to escape is a legal, smart split."""
    hero = _kerendor()
    menu = enumerate_actions(hero, [_foe()])
    assert any(a.kind == "attack" for a in menu), "he is armed"
    [offer] = [a for a in menu if a.kind == "reallocate"]
    assert "All in Wind Riding" in [p.name for p in offer.choice.presets]


# ── standing splits (spec §5.5a) ───────────────────────────────────────────

PATROL = StandingSplit(name="Patrol", points={"wind": 30, "bolt": 30},
                       standard=True, position=0)
OVERDRIVE = StandingSplit(name="Overdrive", points={"wall": 45, "bolt": 60},
                          standard=False, position=1)


def test_a_standing_split_comes_first_and_is_marked():
    [offer] = _splits(_kerendor(standing=(OVERDRIVE, PATROL)))
    first = offer.choice.presets[0]
    assert (first.name, first.standing, first.standard) == ("Patrol", True, True)
    assert first.effect_text == "Blast 6d6, Flight 30m"
    assert first.points == {"bolt": 30, "wind": 30, "wall": 0}
    # Even is the same split as Patrol: collapsed into the player's own.
    assert "Even" not in [p.name for p in offer.choice.presets]


def test_a_standing_split_over_the_reserve_is_left_off_and_named_in_the_brief():
    from kirby_combat.brief_detail import framework_lines
    from kirby_combat.loop.chooser import PhaseSituation

    hero = _kerendor(standing=(PATROL, OVERDRIVE))
    [offer] = _splits(hero)
    assert "Overdrive" not in [p.name for p in offer.choice.presets]
    lines = framework_lines(PhaseSituation(actor=hero, menu=[offer], session=None))
    assert any(ln.strip().startswith("standing split 'Overdrive' no longer fits: ")
               and "105" in ln for ln in lines), lines


def test_standing_splits_survive_a_snapshot():
    import json

    from kirby_combat.serialization import from_dict, to_dict

    hero = _kerendor(standing=(PATROL,))
    again = from_dict(json.loads(json.dumps(to_dict(hero))))
    assert again.state.standing_splits == {FRAMEWORK: (PATROL,)}


def test_a_snapshot_without_standing_splits_is_refused():
    from kirby_combat.serialization import from_dict, to_dict

    record = to_dict(_kerendor())
    del record["standing_splits"]
    with pytest.raises(ValueError, match="standing_splits"):
        from_dict(record)


# ── the brief ──────────────────────────────────────────────────────────────

def test_the_brief_explains_the_framework_and_lists_the_presets():
    from kirby_combat.brief_detail import framework_lines
    from kirby_combat.loop.chooser import PhaseSituation

    hero = _kerendor()
    [offer] = _splits(hero)
    lines = framework_lines(PhaseSituation(actor=hero, menu=[offer], session=None))
    text = "\n".join(lines)
    assert "60 of 60 points in use, 0 free" in text
    assert "6E1 p.404-405" in text
    assert "Lightning Bolt: 60 AP, variable" in text and "now Blast 12d6" in text
    assert "Wall of Wind: 45 AP, fixed" in text and "off" in text
    assert "All in Wind Riding: Flight 60m" in text
    assert ("Wall of Wind + remainder: Resistant Protection 15 PD/15 ED, "
            "Blast 3d6") in text


# ── once a Phase (6E1 p.410) ───────────────────────────────────────────────

class _ResplitsFirst:
    """Takes the first preset of a split offer; otherwise the first offer."""

    def __init__(self):
        self.menus = []

    def give_orders(self, page):
        return KEEP_ORDERS

    def choose(self, situation):
        if getattr(situation, "out_of_turn", None) is not None:
            return situation.menu[0].action_id
        self.menus.append([a.kind for a in situation.menu])
        for a in situation.menu:
            if a.kind == "reallocate":
                return a.action_id + a.choice.answer(a.choice.presets[0].points)
        return situation.menu[0].action_id


def test_after_a_resplit_this_phase_there_is_no_offer():
    chooser = _ResplitsFirst()
    hero = _kerendor()
    hero = replace(hero, state=replace(hero.state, statuses=set()))
    foe = fighter("foe", side=Side.named("villains"), dex=5)
    first = run_phase(encounter_of(hero, foe), chooser,
                      roller=RandomRoller(seed=1), on_unresolvable="raise")
    assert first.kind == "reallocate"
    assert first.session.combatants["kerendor"].state.slot_points[FRAMEWORK] == {
        "bolt": 0, "wind": 60, "wall": 0}
    again = Encounter(id="e", turn=first.session.timeline.turn,
                      segment=first.session.timeline.segment,
                      sessions=[first.session])
    second = run_phase(again, chooser, roller=RandomRoller(seed=2),
                       on_unresolvable="raise")
    assert second.actor_id == "kerendor"
    assert "reallocate" in chooser.menus[0]
    assert "reallocate" not in chooser.menus[1]


# ── fixed-only Multipowers keep whole-set offers ───────────────────────────

def _fixed_only(reserve, costs, *, on):
    from kirby_combat.models import FrameworkView, PricedSlotView, SlotView
    from kirby_combat.hero_view import SlotEffect, SlotStep

    def view(priced):
        def slot(i, cost):
            plain = dict(slot_id=f"s{i}", name=f"Trick {i}", active_points=cost,
                         variable=False, kind="other")
            if not priced:
                return SlotView(**plain)
            return PricedSlotView(**plain, steps=(
                SlotStep(0, "", SlotEffect.nothing()),
                SlotStep(cost, f"Trick {i}", SlotEffect.nothing())))
        return FrameworkView(
            framework_id="fw1", xmlid="MULTIPOWER", name="Brick Tricks",
            kind="multipower", reserve_or_pool=reserve,
            slots=[slot(i, c) for i, c in enumerate(costs, 1)])

    c = fighter("lad", side=Side.named("x"))
    c = replace(c, state=replace(c.state, slot_points={"fw1": {
        f"s{i}": (cost if f"s{i}" in on else 0)
        for i, cost in enumerate(costs, 1)}}))
    c.framework_view = lambda: [view(False)]              # type: ignore[method-assign]
    c.priced_framework_view = lambda: [view(True)]        # type: ignore[method-assign]
    return c


def test_a_fixed_only_multipower_offers_no_set_over_the_reserve():
    from kirby_combat.framework import split_of_action

    offers = _splits(_fixed_only(45, [45, 30, 20, 44], on={"s1"}))
    assert offers
    costs = {"s1": 45, "s2": 30, "s3": 20, "s4": 44}
    for offer in offers:
        fw, tail = split_of_action(offer.action_id, "reallocate_slots")
        assert fw == "fw1"
        drawn = sum(int(t.split("@")[1]) for t in tail.split("+") if t)
        assert drawn <= 45, offer.action_id
        for term in tail.split("+"):
            sid, pts = term.split("@")
            assert int(pts) == costs[sid], "a fixed slot is on at its full AP"


def test_a_multipower_with_one_variable_slot_is_still_offered_a_resplit():
    """6E1 p.405: a lone variable slot can be dialled anywhere from 0 to its
    Active Points, so it is a split to state even with nothing to share."""
    from kirby_combat.hero_view import SlotEffect, SlotStep
    from kirby_combat.models import FrameworkView, PricedSlotView, SlotView

    def view(priced):
        plain = dict(slot_id="v", name="Dial", active_points=30,
                     variable=True, kind="other")
        slot = (PricedSlotView(**plain, steps=tuple(
            SlotStep(p, f"Dial {p}", SlotEffect.nothing()) for p in (0, 10, 20, 30)))
            if priced else SlotView(**plain))
        return FrameworkView(framework_id="one", xmlid="MULTIPOWER", name="Knob",
                             kind="multipower", reserve_or_pool=30, slots=[slot])

    c = fighter("solo", side=Side.named("x"))
    c = replace(c, state=replace(c.state, slot_points={"one": {"v": 10}}))
    c.framework_view = lambda: [view(False)]              # type: ignore[method-assign]
    c.priced_framework_view = lambda: [view(True)]        # type: ignore[method-assign]
    [offer] = _splits(c)
    assert offer.summary == "Re-split Knob (30 reserve): now Dial 10"
    assert [p.name for p in offer.choice.presets] == ["All in Dial"]
