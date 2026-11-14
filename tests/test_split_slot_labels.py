"""A split's words tell its slots apart.

Two slots can be the same power at the same dice, differing only in their
Advantages; an unnamed slot used to be called by its bare alias ("Blast"),
so its presets read alike and a re-split read like a no-op. An unnamed slot
is now labelled with kirby-cost's words for it (`slot_words`: the power and
its Advantages), a named one keeps its name, and what a split buys names
each slot at its rung.

PowerLad (one of the maintainer's own characters) supplies the Multipower;
two unnamed Blasts, one with 0 END, are added to a copy of his build doc.
"""
from __future__ import annotations

import copy

from kirby_cost.io.build_json import build_from_json

from kirby_combat.hero_view import HeroCombatant
from kirby_combat.split_menu import opening_offer
from tests.corpus import require_authored_doc

MP = "1727271632187"            # PowerLad's Multipower
ZERO_END = "9000000000011"
PLAIN = "9000000000014"


def _blast(slot_id: str, modifiers: list[dict]) -> dict:
    out = {"id": slot_id, "xmlid": "ENERGYBLAST", "levels": 6, "base_cost": 0.0,
           "level_cost": 5.0, "level_value": 1.0, "alias": "Blast", "input": "ED",
           "affects_primary": False, "parent": MP}
    if modifiers:
        out["modifiers"] = modifiers
    return out


def _lad() -> HeroCombatant:
    doc = copy.deepcopy(require_authored_doc("PowerLad"))
    doc["powers"] += [
        _blast(ZERO_END, [{"xmlid": "REDUCEDEND", "option_id": "ZERO",
                           "base_cost": 0.5, "alias": "Reduced Endurance"}]),
        _blast(PLAIN, []),
    ]
    return HeroCombatant.from_build(build_from_json(doc), id="lad")


def _opening():
    choice, _summary = opening_offer(_lad().priced_framework(MP), ())
    return choice


def test_unnamed_slots_are_named_by_what_they_are():
    names = {s.slot_id: s.name for s in _lad().priced_framework(MP).slots}
    assert names[ZERO_END] == "Blast 6d6, Reduced Endurance (0 END; +1/2)"
    assert names[PLAIN] == "Blast 6d6"


def test_a_named_slot_keeps_its_name():
    names = {s.slot_id: s.name for s in _lad().priced_framework(MP).slots}
    assert names["1727355441687"] == "The Big Wrap-Up"


def test_no_two_presets_share_a_name_or_words():
    presets = _opening().presets
    assert len({p.name for p in presets}) == len(presets)
    assert len({p.effect_text for p in presets}) == len(presets)


def test_a_named_slot_reads_as_name_and_rung():
    by_name = {p.name: p.effect_text for p in _opening().presets}
    assert by_name["The Big Wrap-Up"] == "The Big Wrap-Up: Entangle 3d6, 6 PD/6 ED"


def test_an_unnamed_slot_at_its_full_rung_reads_as_its_label_alone():
    by_name = {p.name: p.effect_text for p in _opening().presets}
    label = "Blast 6d6, Reduced Endurance (0 END; +1/2)"
    assert by_name[label] == label
