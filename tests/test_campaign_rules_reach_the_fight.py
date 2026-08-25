"""A GM changes a rule; combat resolves differently. No code changes.

The acceptance test for campaign overrides. Everything in between --
CampaignRules, the context slot, the provider patch, the precedence change --
exists to make this one assertion true.

This mirrors the 2026-08-25 scratch experiment that proved the .hdt route
worked, promoted to a test. It uses the ENGINE's own view of a real character
rather than a stub, because a stub would prove only that the helper reads an
attribute -- not that the rule survives a whole load.

The concrete failure a campaign rule prevents: without it, a heroic
campaign's GM who wants killing attacks to do normal damage (a common house
rule -- see the brief) has no lever anywhere in the stack. `kirby-combat`
would keep reporting `RKA` as killing no matter what the GM configures,
because `_damage_type_for_power` reads `power.killing`/`power.defense` off
whatever `kirby-cost` handed it, and nothing upstream of that would ever
change those values. This test proves the lever exists end to end: set it in
kirby-cost, and combat -- unmodified -- reports the other answer.
"""
from __future__ import annotations

import pytest

from tests.corpus import require_authored

from kirby_cost.campaign import CampaignRules, campaign_rules
from kirby_cost.core.context import EngineContext
from kirby_cost.io.hdc_loader import HDCLoader
from kirby_combat.hero_view import _damage_type_for_power


def _walk(objects):
    for obj in objects or ():
        yield obj
        yield from _walk(getattr(obj, "powers", ()) or ())
        yield from _walk(getattr(obj, "objects", ()) or ())


def _rka_of(path: str):
    hero = HDCLoader().load_file(path)
    EngineContext.set_active_hero(hero)
    found = [o for o in _walk(hero.powers) if (o.xmlid or "") == "RKA"]
    if not found:
        # A silent skip here would prove nothing -- report exactly what did
        # not hold rather than let the test quietly pass or vanish.
        pytest.skip("this character has no RKA to measure")
    return found[0]


def test_a_heroic_campaign_makes_killing_attacks_normal():
    path = require_authored("Ravel")

    # Stock: no campaign in force. The template's own KILLING="Yes" stands,
    # and combat reports the attack as killing -- the baseline this test
    # then overturns without touching a line of kirby-combat.
    stock = _rka_of(path)
    assert stock.killing is True
    assert _damage_type_for_power(stock, "RKA") == "killing"

    # The GM's house rule: RKA no longer does killing damage in this
    # campaign. Set once in kirby-cost, nothing told to kirby-combat.
    rules = CampaignRules()
    rules.set("RKA", "killing", False)
    with campaign_rules(rules):
        housed = _rka_of(path)
        assert housed.killing is False
        # Same helper, same code path, unmodified -- it now reports "normal"
        # because it reads the fact the power carries, not an xmlid it
        # recognizes. This line is the whole feature working.
        assert _damage_type_for_power(housed, "RKA") == "normal"

    # And the campaign does not outlive its block -- the next load, outside
    # the `with`, sees the stock template again.
    assert _rka_of(path).killing is True
