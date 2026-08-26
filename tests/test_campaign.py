"""Tests for Campaign and template resolution.

Verbatim from the task-4 brief.
"""
from dataclasses import replace

from kirby_combat.campaign import Campaign, resolve_template
from kirby_combat.encounter import Encounter
from kirby_combat.session.tie_rule import TieRule
from kirby_combat.template import DEFAULT_TEMPLATE, RAW_HEROIC, RAW_SUPERHEROIC


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
                 template=replace(DEFAULT_TEMPLATE, tie_rule=TieRule.INT_THEN_PRE))
    assert resolve_template(c, Encounter(id="e1")).tie_rule is TieRule.INT_THEN_PRE
