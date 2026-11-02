"""A power bought Self Only is never fired at anyone else.

HD's custom advantage or limitation is XMLID="MODIFIER", and its name is the
whole of its meaning. The Destroid's Self Destruct System is "RKA 8d6; 1
Charge which Never Recovers (-4), Self Only (-2), No Range (-1/2)": it blows
the Destroid up and nobody else. The engine read no custom limitation at all,
so it offered the RKA as an ordinary attack, and in a local fight the Destroid
put 57 STUN into Talisman with it and kept fighting.

When a Destroid sets it off (to avoid capture, or when it judges the squad is
lost) is not built, so the power is not offered: refused like any other part
the engine cannot carry out (`power_modifiers.unbuilt_reasons`).
"""
from __future__ import annotations

import pytest

from kirby_combat.power_modifiers import (
    CustomLimitation, custom_limitations_of, unbuilt_reasons,
)
from tests.corpus import require_template

_CHARS = [{"xmlid": x, "levels": 0} for x in (
    "STR", "DEX", "CON", "BODY", "STUN", "END", "SPD", "PD", "ED", "REC", "OCV", "DCV")]


def _hero(*powers):
    from kirby_cost.io.build_json import build_from_json

    return build_from_json({
        "name": "Destroid", "template": "Main6E",
        "base_points": 400, "disad_points": 75, "experience": 0,
        "characteristics": _CHARS, "powers": list(powers),
        "skills": [], "perks": [], "talents": [], "disadvantages": [],
    })


def _attacks(*powers):
    from kirby_combat.hero_view import HeroCombatant

    return {a.name: a for a in HeroCombatant.from_build(_hero(*powers), id="d").attacks}


def _self_destruct(alias):
    return {"id": "sd", "xmlid": "RKA", "name": "Self Destruct System", "levels": 8,
            "input": "ED", "modifiers": [
                {"id": "nr", "xmlid": "NORANGE", "base_cost": -0.5},
                {"id": "so", "xmlid": "MODIFIER", "base_cost": -2.0, "alias": alias},
            ]}


@pytest.fixture(autouse=True)
def _template():
    require_template()


def test_the_build_names_it_self_only():
    (power,) = _hero(_self_destruct("Self Only")).powers
    assert custom_limitations_of(power) == frozenset({CustomLimitation.SELF_ONLY})


def test_the_name_is_read_as_written_whatever_its_case():
    (power,) = _hero(_self_destruct("self only")).powers
    assert custom_limitations_of(power) == frozenset({CustomLimitation.SELF_ONLY})


def test_a_self_only_attack_is_not_offered():
    view = _attacks(_self_destruct("Self Only"))["Self Destruct System"]
    assert view.self_only is True
    assert any("Self Only" in why for why in unbuilt_reasons(view))


def test_a_custom_limitation_it_does_not_read_changes_nothing():
    """Most custom limitations are circumstance the engine does not model
    ("Only When In Contact With The Ground"); they stay as they were."""
    view = _attacks(_self_destruct("Only When Angry"))["Self Destruct System"]
    assert view.self_only is False
    assert unbuilt_reasons(view) == []
