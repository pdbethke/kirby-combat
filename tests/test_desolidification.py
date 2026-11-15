"""Desolidification: switched on, kept up, and what it lets through.

Ravel (PeterB's) has "Dissapate", a 40-point Desolidification slot in his
Multipower "Maleable Sting Body". Before this, the engine never offered it
and nothing it did changed a fight: the power appeared only in a Lockout
comment and in Dispel.

THE RULES (6E1 unless marked; paraphrased, this project ships no rules text):

  * Turning a power on or off is a Zero Phase Action, and turning a given
    power on can be done once in a Phase (6E2 p.20).
  * It is a Constant power: END every Phase it stays up (p.129-130), down
    when he is Stunned or Knocked Out as a Segment ends (p.347), when he
    Recovers (6E2 p.131), or when its Multipower slot loses the reserve
    (p.402) --- the upkeep every kept-up power shares (`kept_up`).
  * While desolid he is immune to most physical and energy attacks,
    Drains and AVADs included. What still reaches him: Mental Powers,
    Sense-Affecting Powers, Presence Attacks, attacks through his
    breathing, Adjustment Powers bought against Desolidification, and
    anything bought with Affects Desolidified (p.192).
  * While desolid he cannot affect the solid world: his attacks on solid
    targets do nothing, Mental and Sense-Affecting Powers included, unless
    bought with Affects Physical World (p.193).

RULINGS, labelled where they are made in `kirby_combat/desolidification.py`:
a Presence Attack is not an attack through the physical world, so a desolid
man may still make one; "attacks through breathing" and "Adjustment Powers
bought against Desolidification" are not readable off a build and are not
let through.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from kirby_combat.desolidification import (
    DESOLIDIFY, DROP_DESOLID, is_desolid, reaches_a_desolid_target,
    reaches_the_solid_world,
)
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.loop.run import _situation_for
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

from tests.corpus import require_authored

MULTIPOWER = "1648348957819"     # "Maleable Sting Body"
DISSAPATE = "1648350930595"      # Desolidification, 40 points
STRING_STORM = "1648350992201"   # Blast, 45


def _ravel(**points: int) -> HeroCombatant:
    hero = replace(HeroCombatant.from_build(require_authored("Ravel"), id="ravel"),
                   side=Side.named("ravel"))
    split = {s.slot_id: 0 for f in hero.framework_view()
             if f.framework_id == MULTIPOWER for s in f.slots}
    split.update(points)
    return replace(hero, state=replace(hero.state, slot_points={MULTIPOWER: split}))


def _session(ravel: HeroCombatant):
    bokor = replace(HeroCombatant.from_build(require_authored("Bokor"), id="bokor"),
                    side=Side.named("bokor"))
    template = CombatTemplate.default_6e_superheroic()
    s = CombatSession.create(id="s", scene=None, template=template,
                             dice_roller=RandomRoller(seed=3),
                             combatants=[ravel, bokor]).start()
    return s, template


def _menu(session, who):
    return _situation_for(session, who).menu


def _take(session, template, who, kind):
    action = next(a for a in _menu(session, who) if a.kind == kind)
    return resolve_chosen(session, session.combatants[who], action,
                          template=template, roller=RandomRoller(seed=1)).session


@pytest.fixture
def dissapate_on():
    return _session(_ravel(**{DISSAPATE: 40}))


class TestSwitchingItOn:
    def test_offered_when_his_slot_holds_it(self, dissapate_on):
        s, _ = dissapate_on
        assert DESOLIDIFY in {a.kind for a in _menu(s, "ravel")}

    def test_not_offered_when_the_slot_holds_nothing(self):
        s, _ = _session(_ravel(**{STRING_STORM: 45}))
        assert DESOLIDIFY not in {a.kind for a in _menu(s, "ravel")}

    def test_taking_it_makes_him_desolid_and_costs_end(self, dissapate_on):
        s, template = dissapate_on
        before = s.combatants["ravel"].state.current_end
        s = _take(s, template, "ravel", DESOLIDIFY)
        assert is_desolid(s, "ravel")
        assert s.combatants["ravel"].state.current_end < before

    def test_once_desolid_he_is_offered_solid_again_and_not_desolid(self, dissapate_on):
        s, template = dissapate_on
        s = _take(s, template, "ravel", DESOLIDIFY)
        kinds = {a.kind for a in _menu(s, "ravel")}
        assert DROP_DESOLID in kinds
        assert DESOLIDIFY not in kinds

    def test_turning_it_on_is_once_a_phase(self, dissapate_on):
        """6E2 p.20: off again, but not back on in the same Phase."""
        s, template = dissapate_on
        s = _take(s, template, "ravel", DESOLIDIFY)
        s = _take(s, template, "ravel", DROP_DESOLID)
        assert not is_desolid(s, "ravel")
        assert DESOLIDIFY not in {a.kind for a in _menu(s, "ravel")}


class TestWhatReachesHim:
    @pytest.fixture
    def desolid(self, dissapate_on):
        s, template = dissapate_on
        return _take(s, template, "ravel", DESOLIDIFY)

    def _at_ravel(self, s):
        return {a.kind for a in _menu(s, "bokor") if a.target_id == "ravel"}

    def test_a_solid_bokor_cannot_hit_or_grab_him(self, dissapate_on, desolid):
        solid_s, _ = dissapate_on
        assert {"attack", "grab", "drain"} & self._at_ravel(solid_s)
        assert not {"attack", "grab", "drain", "strike", "haymaker",
                    "entangle"} & self._at_ravel(desolid)

    def test_mental_flash_and_presence_still_reach_him(self, desolid):
        kinds = self._at_ravel(desolid)
        assert {"mental_blast", "flash", "presence_attack"} <= kinds


class TestWhatHeReaches:
    def test_a_desolid_ravel_cannot_attack_solid_bokor(self, dissapate_on):
        s, template = dissapate_on
        s = _take(s, template, "ravel", DESOLIDIFY)
        at_bokor = {a.kind for a in _menu(s, "ravel") if a.target_id == "bokor"}
        assert not {"attack", "grab", "mental_blast", "flash", "strike"} & at_bokor

    def test_but_he_may_still_make_a_presence_attack(self, dissapate_on):
        s, template = dissapate_on
        s = _take(s, template, "ravel", DESOLIDIFY)
        at_bokor = {a.kind for a in _menu(s, "ravel") if a.target_id == "bokor"}
        assert "presence_attack" in at_bokor


class TestTheAdvantages:
    """The two Advantages the page names, read off the attack's source power."""

    def _power(self, *xmlids):
        return SimpleNamespace(assigned_modifiers=[SimpleNamespace(xmlid=x) for x in xmlids])

    def test_affects_desolidified_reaches_a_desolid_target(self):
        assert reaches_a_desolid_target("attack", self._power("AFFECTSDESOLID"))
        assert not reaches_a_desolid_target("attack", self._power())

    def test_affects_physical_world_reaches_the_solid_world(self):
        assert reaches_the_solid_world("attack", self._power("AFFECTSPHYSICALWORLD"))
        assert not reaches_the_solid_world("attack", self._power())
        assert not reaches_the_solid_world("mental_blast", self._power())
