"""No default combat template, anywhere.

Which optional rules a fight runs under is the campaign's decision, and a
default is that decision made silently by the engine: an Encounter with no
template ran under `DEFAULT_TEMPLATE` (Superheroic) whatever the session it
held said, so a heroic sweep charged no END until the caller noticed
(2026-10-29). Every switch on `CombatTemplate` is stated by whoever builds
one; a Campaign names its template; an Encounter takes its template from
itself or its Campaign, and raises when it has neither.
"""
from __future__ import annotations

import dataclasses

import pytest

import kirby_combat.template as template_module
from kirby_combat.campaign import Campaign
from kirby_combat.encounter import Encounter
from kirby_combat.endurance import tracks_endurance
from kirby_combat.resolution.hit_location import effect_for, uses_hit_locations
from kirby_combat.resolution.knockback import compute_knockback
from kirby_combat.template import RAW_HEROIC, RAW_SUPERHEROIC, CombatTemplate


def test_every_switch_on_a_template_is_stated():
    missing = [f.name for f in dataclasses.fields(CombatTemplate)
               if f.default is not dataclasses.MISSING
               or f.default_factory is not dataclasses.MISSING]
    assert missing == []
    with pytest.raises(TypeError):
        CombatTemplate(name="half a template")  # type: ignore[call-arg]


def test_there_is_no_default_template_and_no_rules_blob():
    assert not hasattr(template_module, "DEFAULT_TEMPLATE")
    assert "custom_rules" not in {f.name for f in dataclasses.fields(CombatTemplate)}


def test_a_campaign_names_its_template():
    with pytest.raises(TypeError):
        Campaign(id="c", name="c")  # type: ignore[call-arg]
    assert Campaign(id="c", name="c", template=RAW_HEROIC).template is RAW_HEROIC


def _fight(template, sid="s"):
    from kirby_combat.session.combat_session import CombatSession

    return CombatSession.create(id=sid, combatants=[], scene=None,
                                template=template, dice_roller=None)


def test_an_encounter_with_nothing_to_read_its_template_from_says_so():
    enc = Encounter(id="e", turn=1, segment=12, sessions=[])
    with pytest.raises(ValueError, match="template"):
        enc._resolve_template(None)
    assert Encounter(id="e", turn=1, segment=12, sessions=[],
                     template=RAW_HEROIC)._resolve_template(None) is RAW_HEROIC


def test_an_encounter_plays_by_its_fights_template():
    """Not a default: every fight states its template, and an Encounter of
    heroic fights runs heroic. It used to run Superheroic."""
    enc = Encounter(id="e", turn=1, segment=12, sessions=[_fight(RAW_HEROIC)])
    assert enc._resolve_template(None) is RAW_HEROIC


def test_an_encounter_that_contradicts_its_fights_says_so():
    mixed = Encounter(id="e", turn=1, segment=12,
                      sessions=[_fight(RAW_HEROIC, "a"), _fight(RAW_SUPERHEROIC, "b")])
    with pytest.raises(ValueError, match="different templates"):
        mixed._resolve_template(None)
    contradicted = Encounter(id="e", turn=1, segment=12,
                             sessions=[_fight(RAW_HEROIC)], template=RAW_SUPERHEROIC)
    with pytest.raises(ValueError, match="another template"):
        contradicted._resolve_template(None)


def test_the_rules_readers_take_a_template_not_none():
    with pytest.raises(ValueError, match="template"):
        tracks_endurance(None, object())
    with pytest.raises(ValueError, match="template"):
        uses_hit_locations(None, object())
    with pytest.raises(TypeError):
        effect_for("head")  # type: ignore[call-arg]


def test_knockback_reads_its_multiplier_off_the_template():
    """One input, not two that can disagree: the scale is the template's."""
    doubled = dataclasses.replace(RAW_SUPERHEROIC, knockback_multiplier=2.0)
    plain = compute_knockback(body=10, knockback_dice=[1, 1],
                              kb_resistance_m=0, template=RAW_SUPERHEROIC)
    scaled = compute_knockback(body=10, knockback_dice=[1, 1],
                               kb_resistance_m=0, template=doubled)
    assert scaled.distance_m == 2 * plain.distance_m
