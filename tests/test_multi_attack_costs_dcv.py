"""A multi-shot maneuver costs the attacker half their DCV.

6E2 p.71 (Multiple Attack), p.73 (Rapid Fire), p.56 (Sweep): all three buy
extra attacks with the actor's own defence. That ½ DCV is the PRICE of the
extra shots.

IT WAS NOT BEING CHARGED. `MultipleAttack.compute` returns
`dcv_factor=0.5`, the resolver recorded it, and nothing read it -- only
Stunned and Presence were registered in `_CV_MODIFIER_SOURCES`. So the
maneuver had an OCV cost and no defensive one, which makes it strictly
better than a single attack whenever more than one enemy is in front of
you.

FOUND BY THE O.K. CORRAL BENCHMARK. With the OCV ladder finally visible on
the menu the model still chose `multiple_attack` in 10 of 12 Phases -- and
it was RIGHT to. Against DCV 4 the ladder 5/3/1/-1 is worth about 1.6
expected hits against 0.74 for a single shot. The maneuver was not being
over-chosen by a confused model; it was UNDER-PRICED by the engine.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.cv_modifiers import effective_dcv_for
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import ActionResolved, make_author_combatant
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

MANEUVERS = ("multiple_attack", "rapid_fire", "sweep")


def _c(name: str, spd: int = 4):
    return synthetic_combatant(
        id=name, name=name, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=spd, dex=20, ego=15, str_=15, con=18, pre=15, rec=6,
        pd=5, ed=5, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=40,
    )


def _session():
    return CombatSession.create(
        id="s", combatants=[_c("alice"), _c("bob")], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
    ).start()


def _took(session, who: str, kind: str, segment: int = 12):
    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(who), declaration_event_id="",
        result_payload={"kind": kind, "segment": segment, "hits": 1},
    ))


# ---- The price ----

@pytest.mark.parametrize("kind", MANEUVERS)
def test_a_multi_shot_maneuver_halves_the_attackers_dcv(kind):
    session = _session()
    assert effective_dcv_for(session, "alice") == 8

    session = _took(session, "alice", kind)
    assert effective_dcv_for(session, "alice") == 4, (
        f"{kind} must cost the attacker half their DCV"
    )


def test_a_single_attack_costs_nothing():
    """The contrast that makes the price meaningful."""
    session = _took(_session(), "alice", "attack")
    assert effective_dcv_for(session, "alice") == 8


def test_only_the_attacker_pays():
    session = _took(_session(), "alice", "multiple_attack")
    assert effective_dcv_for(session, "bob") == 8


# ---- It compounds, like every other source ----

def test_stunned_AND_multi_attacking_compounds():
    """`cv_modifiers_for` folds sources by multiplication, never by min(),
    so two conditions at once give both penalties."""
    from kirby_combat.cv_modifiers import cv_modifiers_for

    session = _took(_session(), "alice", "sweep")
    mods = cv_modifiers_for(session, "alice")
    assert mods.dcv_factor == 0.5


# ---- It clears ----

def test_the_penalty_lasts_the_phase_and_no_longer():
    """"For the Phase" -- cleared on the next SegmentAdvanced into one of
    this combatant's own Phase segments, the same approximation
    `_is_stunned` makes and for the same reason."""
    from kirby_combat.encounter import Encounter

    session = _took(_session(), "alice", "multiple_attack")
    assert effective_dcv_for(session, "alice") == 4

    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    for _ in range(4):                      # into alice's next Phase
        enc = enc.advance_segment()
    assert effective_dcv_for(enc.sessions[0], "alice") == 8


def test_an_unrelated_combatants_maneuver_does_not_charge_you():
    session = _took(_session(), "bob", "rapid_fire")
    assert effective_dcv_for(session, "alice") == 8


# ---- Why this matters to a chooser ----

def test_the_maneuver_is_no_longer_free():
    """The benchmark's point in one assertion: before this, a Multiple
    Attack bought extra shots and gave up nothing, so taking one was
    always correct. Now it trades defence for offence, which is a
    decision."""
    session = _session()
    before = effective_dcv_for(session, "alice")
    after = effective_dcv_for(_took(session, "alice", "multiple_attack"), "alice")
    assert after < before
