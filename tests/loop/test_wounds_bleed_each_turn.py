"""6E2 p.115's optional Bleeding, on the Segment it belongs to.

    "Whenever a character loses BODY, he will Bleed, thus losing STUN and
    occasionally some extra BODY ... Wounded characters should roll the
    dice on Segment 1 of each Turn."

OPTIONAL BY THE BOOK'S OWN FRAMING -- "In situations where a character
can get immediate medical care, there's no need to use the Bleeding
rules" -- so the template gates it and a superheroic game that never
wanted it is untouched. A gunfight is the case it was written for.

Distinct from p.109's bleeding to DEATH, which is not optional, applies
only at or below 0 BODY, takes BODY rather than STUN, and fires at the
END of Segment 12. Both can hit the same man in the same Turn, which is
why `BleedingSuffered` carries which rule fired.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from dataclasses import replace

from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.encounter import Encounter
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import RAW_HEROIC
from kirby_combat.vitals import apply_vitals_delta
from kirby_dice import RandomRoller

BLEEDING = replace(RAW_HEROIC, use_bleeding_rules=True)


def _turn(template, *, body_lost: int):
    combatants = [fighter("hurt", side=Side.named("a")),
                  fighter("well", side=Side.named("b"))]
    session = CombatSession.create(
        id="w", scene=None, template=template,
        dice_roller=RandomRoller(seed=4), combatants=combatants).start()
    session.combatants["hurt"] = apply_vitals_delta(
        session.combatants["hurt"], body=-body_lost)
    return Encounter(id="e", turn=1, segment=12, sessions=[session],
                     template=template).advance_segment().sessions[0]


def _wound_bleeds(session):
    return [e for e in session.event_log
            if getattr(e, "kind", "") == "BleedingSuffered"
            and e.rule == "wound"]


def test_a_wounded_man_bleeds_stun_when_the_rules_are_on():
    bleeds = _wound_bleeds(_turn(BLEEDING, body_lost=6))
    assert bleeds, "6 BODY lost is 2d6 of STUN a Turn (6E2 p115)"
    assert bleeds[0].stun_lost > 0
    assert bleeds[0].combatant_id == "hurt"


def test_the_optional_rules_stay_off_unless_asked_for():
    """They are optional, and every existing fight ran without them."""
    assert _wound_bleeds(_turn(RAW_HEROIC, body_lost=6)) == []


def test_an_unwounded_man_does_not_bleed():
    assert _wound_bleeds(_turn(BLEEDING, body_lost=0)) == []


def test_the_dice_are_recorded():
    """The extra BODY comes from a six, so a reader has to be able to see
    whether one was rolled."""
    bleeds = _wound_bleeds(_turn(BLEEDING, body_lost=6))
    assert len(bleeds[0].dice) == 2, bleeds[0].dice


def test_a_dying_man_takes_both_rules_in_one_turn():
    """p.109 takes his BODY at the end of Segment 12; p.115 takes his
    STUN on Segment 1. They are different rules and both apply."""
    # Just past 0 BODY -- dying, but not yet Dead. Wound him harder than
    # -max BODY and the bleed-out correctly stops, because a corpse has
    # nothing left to lose.
    session = _turn(BLEEDING, body_lost=12)
    rules = {e.rule for e in session.event_log
             if getattr(e, "kind", "") == "BleedingSuffered"}
    assert rules == {"bleed_out", "wound"}, rules
