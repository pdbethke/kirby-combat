"""Beam — the limitation that says a bullet does not widen.

Spreading trades damage dice for OCV or for area (6E2 p.51): the
character "widens" the attack. A bullet does not widen. The HERO System
Equipment Guide p.69 lists the limitations every firearm is built with
and states it outright:

    "Beam: Bullets can't be Spread, and only make relatively small
     'punctures'..."

THE BUILDS ALREADY SAY SO AND THE ENGINE DROPPED IT. `BEAM` is on the
corral arsenal's firearms --- the Derringers, the Pepperbox, every
pistol --- and `hero_view` parsed `REDUCEDEND`, `NORANGEMODIFIER` and
`CHARGES` beside it while never reading this one. So `spread` was
offered 95 times across the western benchmarks for weapons that cannot
do it, and nothing could have taken it legally.

Same shape as this repo's dominant defect: a modifier the build
declares, carried nowhere, read by nothing.

The gate is on SPREADING only. Beam has other consequences in the book
(it forbids a Killing Attack being used to Grab, among others); this
tests and fixes the one the benchmarks exercise, and does not pretend to
the rest.
"""
from __future__ import annotations

from kirby_combat.models import AttackPower


def _gun(*, beam: bool) -> AttackPower:
    return AttackPower(
        xmlid="RKA", name="Colt revolver", damage_dice=4, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=100.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True, beam=beam,
    )


def test_an_attack_is_not_a_beam_unless_it_says_so():
    """Defaulting False keeps every existing construction site honest: a
    power that does not declare the limitation does not acquire one."""
    assert AttackPower(
        xmlid="EB", name="Blast", damage_dice=4, half_die=False,
        plus_one=False, damage_type="normal", defense_type="pd",
        range_m=50.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0,
    ).beam is False


def test_the_view_carries_BEAM_onto_the_attack():
    """The build declares it; the view must hand it on.

    Asserted on the real `actor.attacks` view rather than on
    `_has_modifier` directly: the first draft of this test invented a
    `_Power` with a `modifiers` attribute, which is not the shape the
    engine uses, and so tested nothing but its own double.
    """
    from tests.test_enumeration import _StubPower, _combatant

    gun = _StubPower(xmlid="RKA", name="Colt revolver", levels=4,
                     assigned_modifiers=[_StubPower(xmlid="BEAM")])
    plain = _StubPower(xmlid="ENERGYBLAST", name="Blast", levels=8)
    actor = _combatant(id="frank", powers=[gun, plain])

    by_name = {ap.name: ap.beam for ap in actor.attacks}
    assert by_name.get("Colt revolver") is True
    assert by_name.get("Blast") is False


def _spread_kinds(*, beam: bool) -> list[str]:
    """Every `spread` offer the REAL enumerator makes for a gunfighter.

    Driving `enumerate_actions` rather than re-checking the condition
    here: a helper that re-implements the gate tests the helper, which is
    how the first draft of this file passed while the engine was
    unchanged.
    """
    from tests.test_enumeration import _StubPower, _combatant
    from kirby_combat.enumeration import enumerate_actions

    mods = [_StubPower(xmlid="BEAM")] if beam else []
    gun = _StubPower(xmlid="RKA", name="Colt revolver", levels=4,
                     assigned_modifiers=mods)
    actor = _combatant(id="frank", powers=[gun])
    enemy = _combatant(id="wyatt")
    return [a.action_id for a in enumerate_actions(actor, [enemy])
            if a.kind == "spread"]


def test_a_beam_weapon_is_offered_no_spread():
    """The corral's own arsenal declares BEAM on every firearm."""
    assert _spread_kinds(beam=True) == []


def test_a_non_beam_attack_is_still_offered_spread():
    """The gate must not quietly remove Spreading from everything --- an
    Energy Blast without the limitation widens exactly as it always did."""
    assert _spread_kinds(beam=False) != []
