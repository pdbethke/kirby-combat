"""Side Effects bite the attacker; Increased Endurance Cost charges more.

6E1 p.395: "Each time the character's attempt to activate or use the power
fails, he suffers the Side Effect", or every use if bought "occurring every
time he uses the power". p.397: "no Attack Roll is necessary ... no
defenses against the Side Effect". p.396 sizes it: Minor 15 Active Points or
a quarter of the power's, Major 30 or half, Extreme 60 or all.

6E1 p.376: Increased Endurance Cost multiplies the END ("x2 END" ... "x10").

The deleted api driver surfaced Side Effects as a flag and charged x2 END
whatever the build said; the engine did neither.
"""
from __future__ import annotations

from shaped import (                                    # tests/loop/shaped.py
    Dice, Picks, armed, encounter_on, payloads, scene_with, shaped_blast,
)
from kirby_combat.endurance import end_cost
from kirby_combat.loop import run_phase
from kirby_combat.power_modifiers import (
    IncreasedEnd, SideEffectSeverity, SideEffectsSpec,
)
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


def _effects(severity=SideEffectSeverity.MINOR, always=False,
             environment_only=False):
    return SideEffectsSpec(severity=severity, always_occurs=always,
                           text="the power arcs back into him", unbuilt=(),
                           environment_only=environment_only)


def _fight(power, template=None):
    scene = scene_with({"a": (0, 0, 0), "b": (6, 0, 0)})
    kw = {} if template is None else {"template": template}
    return encounter_on(scene, armed("a", power, side=VILLAINS, dex=30),
                        armed("b", None, side=HEROES, dex=10), **kw)


def _attack(a, _s):
    return a.kind == "attack" and a.target_id == "b"


def test_a_failed_activation_turns_the_power_on_its_owner():
    """Seam: an 11- Activation Roll fails on 3d6 of 5s = 15. A Minor Side
    Effect on a 20-point power is 15 Active Points (the floor beats a
    quarter of 20) = 3d6 Normal, no defenses: 3d6 of 5s = 15 STUN, 3 BODY."""
    power = shaped_blast("a-bolt", 4, activation_roll=11, active_points=20,
                         side_effects=_effects())
    result = run_phase(_fight(power), Picks(_attack), roller=Dice(face=5),
                       on_unresolvable="raise")
    s = result.session
    side = payloads(s, kind="side_effect")
    assert len(side) == 1
    assert side[0]["dice"] == 3 and side[0]["on_failure"] is True
    st = s.combatants["a"].state
    assert (st.current_stun, st.current_body) == (40 - 15, 12 - 3)
    assert s.combatants["b"].state.current_stun == 40


def test_a_made_activation_costs_him_nothing():
    power = shaped_blast("a-bolt", 4, activation_roll=11, active_points=20,
                         side_effects=_effects())
    result = run_phase(_fight(power), Picks(_attack), roller=Dice(face=3),
                       on_unresolvable="raise")
    assert payloads(result.session, kind="side_effect") == []


def test_an_always_side_effect_lands_on_every_use_sized_to_the_power():
    """Major on an 80-point power: half of 80 = 40 beats the floor of 30, so
    8d6 every time it is used, hit or miss."""
    power = shaped_blast("a-bolt", 4, active_points=80,
                         side_effects=_effects(SideEffectSeverity.MAJOR, always=True))
    result = run_phase(_fight(power), Picks(_attack), roller=Dice(face=2),
                       on_unresolvable="raise")
    side = payloads(result.session, kind="side_effect")
    assert [p["dice"] for p in side] == [8]
    assert side[0]["on_failure"] is False


def test_increased_endurance_cost_multiplies_the_rounded_end():
    """6E1 p.368's Pulsar: 4d6 (20 Active Points, 2 END) at x3 END costs 6."""
    base = shaped_blast("a-bolt", 4, active_points=20)
    tripled = shaped_blast("a-bolt", 4, active_points=20,
                           increased_end=IncreasedEnd(multiplier=3, unbuilt=()))
    assert end_cost(base) == 2
    assert end_cost(tripled) == 6


def test_the_attacker_pays_it_in_a_fight():
    """Seam: a heroic campaign counts END (`manage_endurance`), so the x3
    Blast takes 6 END off him through `run_phase`."""
    from kirby_combat.template import RAW_HEROIC as heroic
    tripled = shaped_blast("a-bolt", 4, active_points=20,
                           increased_end=IncreasedEnd(multiplier=3, unbuilt=()))
    result = run_phase(_fight(tripled, template=heroic), Picks(_attack),
                       roller=Dice(face=3), on_unresolvable="raise")
    spends = [e.end for e in result.session.event_log
              if e.kind == "VitalsChanged" and e.combatant_id == "a"
              and e.reason == "end_spent"]
    assert spends == [-6]


def test_a_circumstantial_increase_is_not_offered():
    """6E1 p.376's "Only In Certain Circumstances" names the circumstance in
    words; the engine cannot judge it, so the power is not on the menu."""
    odd = shaped_blast("a-bolt", 4, increased_end=IncreasedEnd(
        multiplier=2, unbuilt=("Increased Endurance Cost only in certain circumstances",)))
    chooser = Picks(lambda a, _s: False)
    run_phase(_fight(odd), chooser, roller=Dice(face=3), on_unresolvable="raise")
    assert not [a for a in chooser.menus[0]
                if getattr(a, "_attack_view", None) is not None
                and a._attack_view.source_id == "a-bolt"]


def test_an_environment_only_side_effect_happens_and_hurts_nobody():
    """6E1 p.396: a Side Effect on "the environment around the character
    instead of the character himself" should "rarely, if ever" damage others
    or give any combat advantage. It was not offered at all; now the power is
    offered, the Side Effect is recorded on its occasion (here: always), and
    nobody's STUN moves but the target's from the Blast itself."""
    from kirby_combat.attack_shapes import offer_is_buildable

    power = shaped_blast("a-bolt", 4, active_points=80,
                         side_effects=_effects(always=True, environment_only=True))
    enc = _fight(power)
    chooser = Picks(_attack)
    result = run_phase(enc, chooser, roller=Dice(face=2),
                       on_unresolvable="raise")
    assert result.kind == "attack"
    side = payloads(result.session, kind="side_effect")
    assert len(side) == 1 and side[0]["on_environment"] is True
    assert side[0]["stun_dealt"] == 0 and side[0]["target_id"] is None
    assert result.session.combatants["a"].state.current_stun == 40
    assert any(offer_is_buildable(enc.sessions[0], "a", a)
               for a in chooser.menus[0] if a.kind == "attack")
