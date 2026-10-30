"""Tests for Campaign and template resolution.

Verbatim from the task-4 brief.
"""
from dataclasses import replace

from kirby_combat.campaign import Campaign, resolve_template
from kirby_combat.encounter import Encounter
from kirby_combat.session.tie_rule import TieRule
from kirby_combat.template import RAW_HEROIC, RAW_SUPERHEROIC


def test_encounter_without_a_template_inherits_the_campaign_default():
    c = Campaign(id="c1", name="Dark Champions", template=RAW_HEROIC)
    assert resolve_template(c, Encounter(id="e1")) is RAW_HEROIC


def test_an_encounter_template_overrides_the_campaign():
    c = Campaign(id="c1", name="X", template=RAW_HEROIC)
    e = Encounter(id="e1", template=RAW_SUPERHEROIC)
    assert resolve_template(c, e) is RAW_SUPERHEROIC


def test_resolution_carries_the_campaign_tie_rule_to_the_encounter():
    """The concrete payoff: TieRule was unreachable because nothing
    plumbed a template down to where ordering happens."""
    c = Campaign(id="c1", name="X",
                 template=replace(RAW_SUPERHEROIC, tie_rule=TieRule.INT_THEN_PRE))
    assert resolve_template(c, Encounter(id="e1")).tie_rule is TieRule.INT_THEN_PRE


def test_a_shared_template_cannot_be_changed_in_place():
    """Every Campaign naming RAW_HEROIC holds the same object, so a change
    made through one would be a change to all of them and to the module
    constant. That was guarded by giving each Campaign a deep copy of a
    default template; there is no default now, and the template is frozen.
    A campaign's own rules are a `replace` of the one it starts from."""
    import dataclasses

    import pytest

    a = Campaign(id="a", name="A", template=RAW_HEROIC)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.template.tie_rule = TieRule.INT_THEN_PRE  # type: ignore[misc]
    own = Campaign(id="b", name="B",
                   template=replace(RAW_HEROIC, tie_rule=TieRule.INT_THEN_PRE))
    assert own.template.tie_rule is TieRule.INT_THEN_PRE
    assert RAW_HEROIC.tie_rule is TieRule.DEX_ROLL
