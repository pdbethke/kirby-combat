"""Defences and movement from a Multipower slot follow the split.

6E1 p.404-406: a variable slot holds the points its split gave it and has as
many levels as fit them; a slot holding none is off. The book's own slots
(6E1 p.406, Kerendor): Resistant Protection 15 PD / 15 ED at 9 points is 3 PD /
3 ED; Flight 60m at 20 points is 20m; Flight at 0 is no flight at all.

The character is the corpus's Ravel with extra slots built by kirby-cost
(`build_power_from_spec`) added to his Multipower the way the loader links
them (flat in `hero.powers`, `.parent` the framework). Nothing here prices a
power: where a number is not the book's, it is read off `levels_within`.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from kirby_combat.hero_view import (
    HeroCombatant, SlotEffect, _slot_contribution, _slot_id_of,
)
from kirby_cost.engine.allocation import NotLadderable, levels_within
from kirby_cost.services.power_builder import build_power_from_spec

from tests.corpus import require_authored

FRAMEWORK = "1648348957819"
RP, FLIGHT, TELE, PD_SLOT, FIXED_FLIGHT = "9001", "9002", "9003", "9004", "9005"
NAKED, DR, DN, POWD = "9006", "9007", "9008", "9009"


def _slot(spec: dict, slot_id: str, name: str, *, variable: bool = True):
    power, _active, _real = build_power_from_spec(spec)
    power._id = slot_id                  # the loader's id; read-only otherwise
    power.name = name
    power.ultra = not variable           # how the loader marks a Fixed slot
    return power


def _kerendor() -> HeroCombatant:
    build = require_authored("Ravel")
    framework = next(p for p in build.powers if str(p.id) == FRAMEWORK)
    for power in (
        _slot({"xmlid": "FORCEFIELD", "pd_levels": 15, "ed_levels": 15},
              RP, "Kerendor RP"),
        _slot({"xmlid": "FLIGHT", "levels": 60}, FLIGHT, "Kerendor Flight"),
        _slot({"xmlid": "TELEPORTATION", "levels": 30}, TELE, "Kerendor Blink"),
        _slot({"xmlid": "PD", "levels": 20}, PD_SLOT, "Kerendor PD"),
        _slot({"xmlid": "FLIGHT", "levels": 25}, FIXED_FLIGHT, "Fixed Flight",
              variable=False),
        _slot({"xmlid": "NAKEDMODIFIER", "modifiers": [{"xmlid": "RESISTANT"}]},
              NAKED, "Naked Resistant"),
        _slot({"xmlid": "DAMAGEREDUCTION", "option_id": "LVL50RESISTANT"},
              DR, "Kerendor DR"),
        _slot({"xmlid": "DAMAGENEGATION"}, DN, "Kerendor DN"),
        _slot({"xmlid": "POWERDEFENSE", "levels": 20}, POWD, "Kerendor POWD"),
    ):
        if power.xmlid == "NAKEDMODIFIER":
            power.input = "for 3 PD/3 ED"
        if power.xmlid == "DAMAGEREDUCTION":
            power.input = "Physical"
        power.parent = framework
        build.powers.append(power)
    return HeroCombatant.from_build(build)


def _power(hero: HeroCombatant, slot_id: str):
    return next(p for p in hero._build().powers if str(p.id) == slot_id)


def _split(hero: HeroCombatant, **points: int) -> HeroCombatant:
    """After a SlotsAllocated: the named slots at the given points, every
    other slot of the Multipower off."""
    full = {s.slot_id: 0 for f in hero.framework_view()
            if f.framework_id == FRAMEWORK for s in f.slots}
    full.update({k.removeprefix("s"): v for k, v in points.items()})
    return replace(hero, state=replace(hero.state, slot_points={FRAMEWORK: full}))


def _defence(hero, name):
    return [d for d in hero.defense_view() if d.name == name]


def _move(hero, mode, combat_m=None):
    return [m for m in hero.movement_view()
            if m.mode == mode and (combat_m is None or m.combat_m == combat_m)]


# ── Resistant Protection ────────────────────────────────────────────────────
def test_not_yet_opened_the_slot_reads_as_bought():
    [d] = _defence(_kerendor(), "Kerendor RP")
    assert (d.rpd, d.red) == (15, 15)


def test_book_resistant_protection_at_nine_points_is_three_and_three():
    hero = _split(_kerendor(), **{f"s{RP}": 9})
    [d] = _defence(hero, "Kerendor RP")
    assert (d.rpd, d.red) == (3, 3)                    # 6E1 p.406


def test_a_defence_slot_holding_nothing_gives_no_defence():
    hero = _split(_kerendor(), **{f"s{RP}": 0})
    assert _defence(hero, "Kerendor RP") == []


def test_combat_stats_total_the_split_resistant_protection():
    whole = _split(_kerendor(), **{f"s{RP}": 45}).combat_stats()
    cut = _split(_kerendor(), **{f"s{RP}": 9}).combat_stats()
    off = _split(_kerendor(), **{f"s{RP}": 0}).combat_stats()
    assert (whole.rpd - off.rpd, whole.red - off.red) == (15, 15)
    assert (cut.rpd - off.rpd, cut.red - off.red) == (3, 3)


def test_a_characteristic_bought_in_the_slot_follows_the_split():
    """PD bought as a Power feeds combat_stats() (not defense_view)."""
    off = _split(_kerendor(), **{f"s{PD_SLOT}": 0}).combat_stats().pd
    for points in (20, 8):
        got = _split(_kerendor(), **{f"s{PD_SLOT}": points}).combat_stats().pd
        want = int(levels_within(_power(_kerendor(), PD_SLOT), points, hero=None).power.levels)
        assert got - off == want
    assert (_split(_kerendor(), **{f"s{PD_SLOT}": 8}).combat_stats().pd
            < _split(_kerendor(), **{f"s{PD_SLOT}": 20}).combat_stats().pd)


# ── Movement ────────────────────────────────────────────────────────────────
def test_book_flight_at_twenty_points_is_twenty_metres():
    hero = _split(_kerendor(), **{f"s{FLIGHT}": 20})
    assert _move(hero, "flight", 60.0) == []
    [m] = _move(hero, "flight", 20.0)
    assert m.combat_m == 20.0                          # 6E1 p.406
    assert m.vertical_m == 20.0 and m.active_cost == 20.0


def test_flight_at_nothing_is_no_flight_mode():
    hero = _split(_kerendor(), **{f"s{FLIGHT}": 0})
    assert not [m for m in _move(hero, "flight") if m.combat_m in (60.0, 20.0)]


def test_flight_as_bought_before_the_opening():
    assert _move(_kerendor(), "flight", 60.0)


def test_teleportation_slot_follows_the_split_the_same_way():
    hero = _split(_kerendor(), **{f"s{TELE}": 12})
    [m] = _move(hero, "teleportation")
    assert m.combat_m == float(levels_within(_power(hero, TELE), 12, hero=None).power.levels)
    assert not _move(_split(_kerendor(), **{f"s{TELE}": 0}), "teleportation")


def test_a_fixed_slot_keeps_its_bought_size_while_it_holds_points():
    bought = 25
    hero = _split(_kerendor(), **{f"s{FIXED_FLIGHT}": bought})
    assert _move(hero, "flight", 25.0)
    assert not _move(_split(_kerendor(), **{f"s{FIXED_FLIGHT}": 0}), "flight", 25.0)


def test_running_leaping_and_climbing_are_untouched_by_a_split():
    own = ("running", "leaping", "climbing")
    before = {m.mode: m for m in _kerendor().movement_view() if m.mode in own}
    after = {m.mode: m for m in _split(_kerendor(), **{f"s{FLIGHT}": 0}
                                       ).movement_view() if m.mode in own}
    assert after == before and "climbing" in after


# ── _slot_contribution: a pure function of (power, points) ──────────────────
def test_slot_contribution_is_the_priced_copys_effect():
    hero = _kerendor()
    eff = _slot_contribution(_power(hero, RP), 9, str_for_augmentation=0, hero=None)
    assert isinstance(eff, SlotEffect)
    assert eff.attack is None and eff.movement == []
    [d] = eff.defenses
    assert (d.rpd, d.red) == (3, 3)
    [m] = _slot_contribution(_power(hero, FLIGHT), 20, str_for_augmentation=0, hero=None).movement
    assert m.combat_m == 20.0


def test_slot_contribution_at_nothing_is_empty():
    eff = _slot_contribution(_power(_kerendor(), RP), 0, str_for_augmentation=0, hero=None)
    assert (eff.attack, eff.defenses, eff.movement) == (None, [], [])


def test_slot_contribution_agrees_with_the_views():
    hero = _split(_kerendor(), **{f"s{FLIGHT}": 20, f"s{RP}": 9})
    want_d = _slot_contribution(_power(hero, RP), 9, str_for_augmentation=0, hero=None).defenses
    want_m = _slot_contribution(_power(hero, FLIGHT), 20, str_for_augmentation=0, hero=None).movement
    assert _defence(hero, "Kerendor RP") == want_d
    assert [m for m in hero.movement_view() if m.combat_m == 20.0 and m.mode == "flight"] == want_m


# ── a slot holding nothing is off, whatever its kind (6E1 p.404-405) ────────
def test_a_naked_resistant_slot_at_nothing_adds_no_armour():
    off = _split(_kerendor(), **{f"s{NAKED}": 0}).combat_stats()
    on = _split(_kerendor(), **{f"s{NAKED}": 1}).combat_stats()
    assert (on.rpd - off.rpd, on.red - off.red) == (3, 3)   # as bought


# ── defence kinds that cannot be priced by levels ───────────────────────────
@pytest.mark.parametrize("slot", [DR, DN])
def test_unladderable_defence_slot_is_fine_at_nothing_and_at_full_cost(slot):
    hero = _kerendor()
    full = int(_power(hero, slot).active_cost)
    for points in (0, full):
        got = _split(_kerendor(), **{f"s{slot}": points})
        got.defense_view()
        got.combat_stats()
    assert _defence(_split(_kerendor(), **{f"s{slot}": 0}), "Kerendor DR") == []
    assert _defence(_split(_kerendor(), **{f"s{DR}": 30}), "Kerendor DR")


@pytest.mark.parametrize("slot", [DR, DN])
def test_unladderable_defence_slot_given_a_part_of_its_cost_raises(slot):
    """Not a rule invented here: kirby-cost cannot price it by levels, so a
    partial allocation is refused rather than guessed."""
    hero = _split(_kerendor(), **{f"s{slot}": 2})
    with pytest.raises(NotLadderable):
        hero.defense_view()


def test_a_laddered_defence_kind_follows_the_split():
    hero = _split(_kerendor(), **{f"s{POWD}": 8})
    [d] = _defence(hero, "Kerendor POWD")
    assert d.power_defense == int(levels_within(_power(hero, POWD), 8, hero=None).power.levels)
    assert d.power_defense < 20


# ── the attack a contribution carries keeps the ORIGINAL's slot id ──────────
def test_slot_contribution_attack_keeps_an_idless_slots_own_id():
    hero = _kerendor()
    power, _a, _r = build_power_from_spec({"xmlid": "ENERGYBLAST", "levels": 10})
    power._id = ""                         # no id: the slot id derives from id()
    power.parent = next(p for p in hero._build().powers if str(p.id) == FRAMEWORK)
    eff = _slot_contribution(power, 25, str_for_augmentation=0, hero=None)
    assert eff.attack is not None
    assert eff.attack.slot_id == _slot_id_of(power)
