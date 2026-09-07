"""An Aid raises something and a Drain lowers something.

WHAT WAS WRONG. Adjustment had every piece but one. `AdjustmentApplied` was
emitted, `session/effects.py` folded it correctly, and `AdjustmentFaded`
reduced it every Turn -- and a grep for `adjustment_delta` /
`adjustments_for` OUTSIDE effects.py returned nothing. No stat consumer read
the fold, so the whole chain kept books on an effect that never happened.

These tests assert OUTCOMES, not deltas: a CV that changes, and a target
that gets Stunned by a blow that would otherwise have fallen short. A test
that only checked `net_adjustment` would have passed the entire time the
feature was inert.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.adjustments import (
    adjusted_con, effective_characteristic, net_adjustment,
)
from kirby_combat.cv_modifiers import effective_dcv_for, effective_ocv_for
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import AdjustmentApplied, make_author_engine
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


def _c(name: str, **kw):
    base = dict(
        ocv=8, dcv=8, omcv=5, dmcv=5, spd=4, dex=20, ego=15, str_=15,
        con=18, pre=15, rec=6, pd=5, ed=5, rpd=0, red=0, md=0,
        power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=40,
    )
    base.update(kw)
    return synthetic_combatant(id=name, name=name, **base)


def _session(*combatants):
    return CombatSession.create(
        id="s", combatants=list(combatants) or [_c("alice"), _c("bob")],
        scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
    ).start()


def _adjust(session, target: str, stat: str, delta: int):
    return apply_event(session, AdjustmentApplied(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        target_id=target, stat=stat, delta=delta, fade_rate_per_turn=5,
    ))


# ---- The read surface ----

def test_an_aid_raises_and_a_drain_lowers():
    session = _adjust(_adjust(_session(), "alice", "DEX", +6), "bob", "DEX", -4)
    assert net_adjustment(session, "alice", "DEX") == 6
    assert net_adjustment(session, "bob", "DEX") == -4


def test_a_characteristic_never_goes_negative():
    """6E1 p.139 -- a Drained DEX of -3 is not a thing the rules describe,
    and a negative would poison every roll derived from it. `compute_drain`
    caps a single Drain by the current value; this floor is what holds when
    two of them stack."""
    session = _adjust(_adjust(_session(), "bob", "DEX", -20), "bob", "DEX", -20)
    assert effective_characteristic(session, "bob", "DEX", 20) == 0


def test_the_stat_name_is_read_case_insensitively():
    """An Adjustment records "DCV"; a CV caller works in "dcv"."""
    session = _adjust(_session(), "alice", "DCV", +3)
    assert net_adjustment(session, "alice", "dcv") == 3


# ---- CVs actually change ----

def test_draining_dcv_lowers_the_effective_dcv():
    session = _session()
    assert effective_dcv_for(session, "bob") == 8
    session = _adjust(session, "bob", "DCV", -3)
    assert effective_dcv_for(session, "bob") == 5


def test_aiding_ocv_raises_the_effective_ocv():
    session = _adjust(_session(), "alice", "OCV", +4)
    assert effective_ocv_for(session, "alice") == 12


def test_the_adjustment_applies_BEFORE_a_halving_not_after():
    """An Adjustment changes the CHARACTERISTIC (6E1 p.133/p.139), so a
    Stunned character with a Drained DCV is halved on the already-lowered
    value. 8 -> 4 Drained -> 2 Stunned; halving first would give 4 -> 1."""
    from kirby_combat.actions.recording import resolve_attack_in_session
    from kirby_combat.models import AttackInput, AttackPower, DiceValues

    session = _session(_c("alice"), _c("bob", con=1, pd=0, ed=0))
    power = AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=12, half_die=False,
        plus_one=False, damage_type="normal", defense_type="ed", range_m=100,
        uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
        increased_stun_mult=0, is_ranged=True, source_id="eb",
    )
    session, result = resolve_attack_in_session(
        session,
        AttackInput(
            attacker=session.combatants["alice"], target=session.combatants["bob"],
            power=power, distance_m=None, aim=None,
            dice=DiceValues(to_hit=[1, 1, 1], damage=[6] * 12),
        ),
        CombatTemplate.default_6e_superheroic(),
    )
    assert "Stunned" in result.status_changes, "sanity: bob is Stunned"

    session = _adjust(session, "bob", "DCV", -4)
    assert effective_dcv_for(session, "bob") == 2, "Drained to 4, then halved"


def test_an_unadjusted_combatant_reads_exactly_as_before():
    """Every pre-existing call site must return what it always did."""
    session = _session()
    assert effective_dcv_for(session, "alice") == 8
    assert effective_ocv_for(session, "alice") == 8


# ---- The Stunning check: the sharpest thing a Drain does ----

def test_draining_con_makes_a_blow_stun_that_otherwise_would_not():
    """6E2 p.106 -- Stunning is "STUN done by a single attack exceeds his
    CON". Lowering CON is the whole point of Draining it, and it was inert.
    """
    from kirby_combat.actions.recording import resolve_attack_in_session
    from kirby_combat.models import AttackInput, AttackPower, DiceValues

    power = AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=5, half_die=False,
        plus_one=False, damage_type="normal", defense_type="ed", range_m=100,
        uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
        increased_stun_mult=0, is_ranged=True, source_id="eb",
    )

    def _hit(session):
        return resolve_attack_in_session(
            session,
            AttackInput(
                attacker=session.combatants["alice"],
                target=session.combatants["bob"],
                power=power, distance_m=None, aim=None,
                dice=DiceValues(to_hit=[1, 1, 1], damage=[3] * 5),
            ),
            CombatTemplate.default_6e_superheroic(),
        )

    # 15 STUN against CON 18 -- short of Stunning.
    _, plain = _hit(_session(_c("alice"), _c("bob", con=18, pd=0, ed=0)))
    assert plain.stun_dealt == 15
    assert "Stunned" not in plain.status_changes

    # The same blow against a CON Drained to 12 now exceeds it.
    drained = _adjust(_session(_c("alice"), _c("bob", con=18, pd=0, ed=0)), "bob", "CON", -6)
    assert adjusted_con(drained, drained.combatants["bob"]) == 12
    _, stunned = _hit(drained)
    assert stunned.stun_dealt == 15
    assert "Stunned" in stunned.status_changes, (
        "a Drained CON must make this blow Stun"
    )


def test_aiding_con_makes_a_blow_fail_to_stun():
    """The other direction, so the wiring cannot be one-way."""
    from kirby_combat.actions.recording import resolve_attack_in_session
    from kirby_combat.models import AttackInput, AttackPower, DiceValues

    power = AttackPower(
        xmlid="ENERGYBLAST", name="Blast", damage_dice=5, half_die=False,
        plus_one=False, damage_type="normal", defense_type="ed", range_m=100,
        uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
        increased_stun_mult=0, is_ranged=True, source_id="eb",
    )
    session = _adjust(_session(_c("alice"), _c("bob", con=12, pd=0, ed=0)), "bob", "CON", +8)
    _, result = resolve_attack_in_session(
        session,
        AttackInput(
            attacker=session.combatants["alice"], target=session.combatants["bob"],
            power=power, distance_m=None, aim=None,
            dice=DiceValues(to_hit=[1, 1, 1], damage=[3] * 5),
        ),
        CombatTemplate.default_6e_superheroic(),
    )
    assert result.stun_dealt == 15
    assert "Stunned" not in result.status_changes, "CON 12 Aided to 20 holds"


def test_a_faded_adjustment_stops_affecting_the_stat():
    """The two halves must meet: once the fade takes it to zero, the CV is
    the build's again."""
    from kirby_combat.encounter import Encounter

    session = _adjust(_session(), "bob", "DCV", -3)
    assert effective_dcv_for(session, "bob") == 5

    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    enc = enc.advance_segment()          # the Turn wrap fades it out entirely
    assert effective_dcv_for(enc.sessions[0], "bob") == 8
