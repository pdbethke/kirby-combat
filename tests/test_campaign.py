"""Tests for Campaign and template resolution.

Verbatim from the task-4 brief.
"""
from dataclasses import replace

from kirby_combat.campaign import Campaign, resolve_template
from kirby_combat.encounter import Encounter
from kirby_combat.session.tie_rule import TieRule
from kirby_combat.template import (
    DEFAULT_TEMPLATE,
    RAW_HEROIC,
    RAW_SUPERHEROIC,
    CombatTemplate,
)


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


def test_default_template_is_not_a_shared_mutable_singleton():
    """Reviewer finding: `default_factory=lambda: DEFAULT_TEMPLATE` returns
    the SAME object to every Campaign that doesn't pass `template=`
    explicitly, and CombatTemplate is not frozen -- so mutating one
    campaign's default template silently rewrote every other campaign's,
    and poisoned the module-level DEFAULT_TEMPLATE / RAW_SUPERHEROIC
    constant for the rest of the process. Each Campaign must get its own
    copy of the default.
    """
    a = Campaign(id="a", name="A")
    b = Campaign(id="b", name="B")

    assert a.template is not b.template

    a.template.tie_rule = "MUTATED"

    assert b.template.tie_rule != "MUTATED"
    assert DEFAULT_TEMPLATE.tie_rule != "MUTATED"


def test_default_template_does_not_share_mutable_fields_by_identity():
    """`dataclasses.replace` is a SHALLOW copy -- it re-invokes __init__
    with the SAME field values, so a `replace(DEFAULT_TEMPLATE)` factory
    still hands every Campaign the identical `custom_rules` dict and
    `allowed_hit_locations` list objects DEFAULT_TEMPLATE (and therefore
    RAW_SUPERHEROIC/RAW_HEROIC, and CombatTemplate.default_6e_superheroic(),
    which template.py documents as what CombatSession.create callers use)
    carries. Mutating one campaign's dict/list must not be visible through
    a sibling campaign or through the module-level constants.

    This must fail against a `field(default_factory=lambda:
    replace(DEFAULT_TEMPLATE))` factory and pass only once the factory
    does a deep copy.
    """
    a = Campaign(id="a", name="A")
    b = Campaign(id="b", name="B")

    assert a.template.custom_rules is not b.template.custom_rules
    assert a.template.custom_rules is not DEFAULT_TEMPLATE.custom_rules
    assert a.template.allowed_hit_locations is not b.template.allowed_hit_locations
    assert a.template.allowed_hit_locations is not DEFAULT_TEMPLATE.allowed_hit_locations

    a.template.custom_rules["pwned"] = True
    a.template.allowed_hit_locations.append("head")

    assert "pwned" not in b.template.custom_rules
    assert "pwned" not in DEFAULT_TEMPLATE.custom_rules
    assert "pwned" not in RAW_SUPERHEROIC.custom_rules
    assert "pwned" not in CombatTemplate.default_6e_superheroic().custom_rules

    assert "head" not in b.template.allowed_hit_locations
    assert "head" not in DEFAULT_TEMPLATE.allowed_hit_locations
    assert "head" not in RAW_SUPERHEROIC.allowed_hit_locations
