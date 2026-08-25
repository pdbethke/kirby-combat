"""A campaign's template rules reach the fight without a code change.

kirby-cost reads the .hdt; kirby-combat acts on what kirby-cost emits. That
division is what lets a GM change a rule -- killing attacks that do normal
damage in a heroic campaign, knockback switched off -- by editing the template
their characters are already built against, and have the change show up in
combat. Nothing here should need to know a rule was changed.

This test guards the seam in BOTH directions. Combat must follow the engine's
answer when there is one, and must fall back to its xmlid stubs only for an
object with no such fact at all. Confusing "the template said No" with "the
template said nothing" would silently put the house rule back.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from kirby_combat.hero_view import _damage_type_for_power


def _power(**facts):
    return SimpleNamespace(**facts)


def test_combat_follows_the_engine_when_the_power_states_killing():
    assert _damage_type_for_power(_power(killing=True, defense="NORMAL"), "RKA") == "killing"


def test_a_campaign_that_disarms_killing_attacks_is_obeyed():
    """The house rule. The xmlid still says RKA; the campaign says it does
    normal damage, and the campaign wins."""
    assert _damage_type_for_power(_power(killing=False, defense="NORMAL"), "RKA") == "normal"


def test_mental_comes_from_the_stated_defence_not_from_the_xmlid():
    assert _damage_type_for_power(_power(killing=False, defense="MENTAL"), "EGOATTACK") == "mental"
    # ...and an xmlid combat has never heard of still resolves, because the
    # power carries the fact itself.
    assert _damage_type_for_power(_power(killing=False, defense="MENTAL"), "SANITYDRAIN") == "mental"


@pytest.mark.parametrize("xmlid,expected", [
    ("RKA", "killing"),
    ("HKA", "killing"),
    ("EGOATTACK", "mental"),
    ("ENERGYBLAST", "normal"),
])
def test_a_bare_stub_with_no_stated_facts_still_falls_back_to_the_xmlid(xmlid, expected):
    """Objects built by hand in tests carry no template. They keep working."""
    assert _damage_type_for_power(_power(), xmlid) == expected


def test_the_fallback_is_reachable_only_when_the_facts_are_absent():
    """Proves the two branches are actually distinct -- without this, the
    stated-fact path could be dead code and every test above would still pass
    off the xmlid lists."""
    stated_no = _power(killing=False, defense="NORMAL")
    assert _damage_type_for_power(stated_no, "RKA") != _damage_type_for_power(_power(), "RKA")
