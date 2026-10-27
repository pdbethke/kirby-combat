"""No Range means hand to hand.

6E1 p.131: "If a Power has No Range, the character using it ... only has to
be in HTH Combat range to use it." HD writes the Limitation NORANGE, and
`hero_view` never read it: every No Range power --- 197 of the corpus's
shaped attack views, every Damage Shield among them --- was fired from
across the map at its Active Points in metres. NORANGEMODIFIER is a
different thing (the +1/2 Advantage) and must not be confused with it.
"""
from __future__ import annotations


def test_a_no_range_power_has_no_range():
    from tests.test_enumeration import _StubPower, _combatant

    shield = _StubPower(xmlid="RKA", name="Spikes", levels=1,
                        assigned_modifiers=[_StubPower(xmlid="NORANGE")])
    sniper = _StubPower(xmlid="RKA", name="Rifle", levels=2,
                        assigned_modifiers=[_StubPower(xmlid="NORANGEMODIFIER")])
    plain = _StubPower(xmlid="ENERGYBLAST", name="Blast", levels=8)
    actor = _combatant(id="frank", powers=[shield, sniper, plain])
    by_name = {ap.name: ap for ap in actor.attacks}
    assert by_name["Spikes"].range_m == 0.0 and by_name["Spikes"].is_ranged is False
    assert by_name["Rifle"].is_ranged is True
    assert by_name["Blast"].is_ranged is True


def test_the_view_reads_persistent_and_uncontrolled():
    from tests.test_enumeration import _StubPower, _combatant

    aura = _StubPower(xmlid="RKA", name="Aura", levels=1,
                      assigned_modifiers=[_StubPower(xmlid="PERSISTENT"),
                                          _StubPower(xmlid="UNCONTROLLED")])
    actor = _combatant(id="frank", powers=[aura])
    (view,) = actor.attacks
    assert view.persistent is True and view.uncontrolled is True
