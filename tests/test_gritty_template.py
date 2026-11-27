"""The Gritty template: Western Hero's lethality options, each a 6E2 rule.

Western Hero's Gritty Campaign (book p.168), whose Historical variant names
Tombstone, tells the GM to turn on every optional rule that makes combat
dangerous: Impairing and Disabling Wounds, Bleeding, Hit Locations. 6E2
supplies each as its own optional rule --- Wounding p.110, Impairing and
Disabling p.113-114, Knockdown p.114-115, Bleeding p.115, Critical Hits
p.120 --- and Western Hero p.112 says Knockback "is not ideal for most
Western Hero campaigns". Peter, 2026-11-27: all of them on for the Corral.

Each is its own switch because the book offers each separately, and no
switch has a default: a template that does not say is refused.
"""
from __future__ import annotations

from dataclasses import fields

import pytest

from kirby_combat.template import (
    GRITTY_HEROIC, RAW_HEROIC, TEMPLATES_BY_NAME, CombatTemplate,
)

LETHALITY = ("use_wounding", "use_impairing_disabling", "use_knockdown",
             "use_critical_hits")


def test_gritty_turns_every_lethality_option_on():
    for flag in LETHALITY:
        assert getattr(GRITTY_HEROIC, flag) is True, flag
    assert GRITTY_HEROIC.use_bleeding_rules is True
    assert GRITTY_HEROIC.use_hit_locations is True


def test_gritty_uses_knockdown_not_knockback():
    """Western Hero p.112."""
    assert GRITTY_HEROIC.use_knockback is False


def test_gritty_is_heroic_otherwise():
    """Only the lethality switches differ from RAW Heroic."""
    changed = {f.name for f in fields(CombatTemplate)
               if getattr(GRITTY_HEROIC, f.name) != getattr(RAW_HEROIC, f.name)}
    assert changed == {"name", "use_knockback", "use_bleeding_rules", *LETHALITY}


def test_gritty_is_named_in_the_registry():
    assert TEMPLATES_BY_NAME["6e-heroic-gritty"] is GRITTY_HEROIC


def test_every_other_named_template_leaves_them_off():
    for key, template in TEMPLATES_BY_NAME.items():
        if template is GRITTY_HEROIC:
            continue
        for flag in LETHALITY:
            assert getattr(template, flag) is False, (key, flag)


@pytest.mark.parametrize("flag", LETHALITY)
def test_a_template_must_state_each_one(flag):
    kwargs = {f.name: getattr(RAW_HEROIC, f.name) for f in fields(CombatTemplate)}
    del kwargs[flag]
    with pytest.raises(TypeError):
        CombatTemplate(**kwargs)
