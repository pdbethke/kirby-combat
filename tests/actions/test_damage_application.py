"""Damage lands on the session's combatants.

THE GAP THIS CLOSES. ``resolve_attack_in_session`` computed ``stun_dealt``,
recorded it in the event log, and left ``current_stun`` alone. Every
consumer therefore subtracted damage by hand — the parked kirby-api driver
did it at 15 separate sites, none of which handled both combatant shapes.
A fight could not run more than one exchange out of the engine alone.

HOW IT IS APPLIED, AND WHY NOT IN ``apply_event``. Mutate the combatant,
then log — the same two-step ``_apply_post_12_recovery`` and
``MovementAction.resolve`` already use, the latter commented "apply_event
won't do it for us". ``session/apply.py`` explicitly rejects folding stat
changes into the dispatcher: "combatant stat mutations in apply would force
log replay to mirror combatant state, which is more brittle." These tests
pin the two-step, not an apply-time fold.
"""
from __future__ import annotations

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions.recording import (
    resolve_attack_in_session, resolve_mental_blast_in_session,
)
from kirby_combat.models import AttackInput, AttackPower, DiceValues
from kirby_combat.session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_dice import FakeRoller


def _attacker():
    return synthetic_combatant(
        id="attacker", name="Attacker", ocv=12, dcv=8, omcv=9, dmcv=5,
        spd=4, dex=20, ego=20, str_=10, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=40, max_body=15, max_end=30,
        current_stun=40, current_body=15, current_end=30,
        is_mentalist=True,
        attacks=[AttackPower(
            xmlid="ENERGYBLAST", name="Energy Blast", damage_dice=8,
            half_die=False, plus_one=False,
            damage_type="normal", defense_type="ed", range_m=100,
            uses_str=False, str_min=0,
            armor_piercing=0, penetrating=0, increased_stun_mult=0,
        )],
    )


def _target(stun: int = 40, body: int = 15):
    """DCV 0 and no defenses, so the attack lands and its damage is the
    raw roll — these tests are about where the number goes, not the
    resolution math, which ``test_damage.py`` already covers."""
    return synthetic_combatant(
        id="target", name="Target", ocv=6, dcv=0, omcv=3, dmcv=0,
        spd=3, dex=10, ego=10, str_=10, con=15, pre=10, rec=5,
        pd=0, ed=0, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=40, max_body=15, max_end=30,
        current_stun=stun, current_body=body, current_end=30,
    )


def _session(*combatants) -> CombatSession:
    return CombatSession.create(
        id="s1", combatants=list(combatants), scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def _attack(attacker, target, *, dice):
    """``to_hit=[3,3,3]`` (a 9) is well within range against DCV 0, so these
    attacks always land; ``dice`` fixes the damage total."""
    return AttackInput(
        attacker=attacker, target=target, power=attacker.attacks[0],
        distance_m=0, aim=None,
        dice=DiceValues(to_hit=[3, 3, 3], damage=dice),
    )


# ---- The core: damage reaches session.combatants ----

def test_stun_is_subtracted_from_the_session_combatant():
    a, t = _attacker(), _target(stun=40)
    s = _session(a, t)
    s2, result = resolve_attack_in_session(
        s, _attack(a, t, dice=[3, 3, 3, 3, 3, 3, 3, 3]),
        CombatTemplate.default_6e_superheroic(),
    )
    assert result.hit
    assert result.stun_dealt > 0
    assert s2.combatants["target"].current_stun == 40 - result.stun_dealt


def test_body_is_subtracted_from_the_session_combatant():
    a, t = _attacker(), _target(body=15)
    s = _session(a, t)
    s2, result = resolve_attack_in_session(
        s, _attack(a, t, dice=[6, 6, 6, 6, 6, 6, 6, 6]),
        CombatTemplate.default_6e_superheroic(),
    )
    assert result.body_dealt > 0
    assert s2.combatants["target"].current_body == 15 - result.body_dealt


def test_the_original_session_is_not_mutated():
    a, t = _attacker(), _target(stun=40)
    s = _session(a, t)
    resolve_attack_in_session(
        s, _attack(a, t, dice=[3] * 8), CombatTemplate.default_6e_superheroic(),
    )
    assert s.combatants["target"].current_stun == 40


def test_an_attacker_takes_no_damage_from_their_own_attack():
    """The attacker's STUN and BODY come through untouched.

    This used to assert END was untouched too, with the docstring "END
    cost for an attack is a separate rule and not this change's business"
    -- it was scoping the damage-application change and deferring END, not
    claiming attacks are free. END is now charged (6E1 p.132), so the
    assertion is split: no DAMAGE to the attacker, and exactly the END the
    result priced. Strictly stronger than what it replaced.
    """
    a, t = _attacker(), _target()
    s = _session(a, t)
    s2, result = resolve_attack_in_session(
        s, _attack(a, t, dice=[3] * 8), CombatTemplate.default_6e_superheroic(),
    )
    before, after = s.combatants["attacker"], s2.combatants["attacker"]
    assert (after.current_stun, after.current_body) == (
        before.current_stun, before.current_body
    ), "an attacker takes no damage from their own attack"

    # END is the campaign's call, not this test's: `RAW_SUPERHEROIC` ships
    # `manage_endurance=False` ("END optional"), so nothing is charged
    # here. Computed from the template rather than assumed, so this stays
    # true whichever template the fixture moves to.
    from kirby_combat.actions.recording import _tracks_endurance

    template = CombatTemplate.default_6e_superheroic()
    expected = result.end_spent if _tracks_endurance(template, a) else 0
    assert before.current_end - after.current_end == expected


# ---- Damage accumulates across exchanges: the thing that was impossible ----

def test_successive_attacks_accumulate():
    a, t = _attacker(), _target(stun=40)
    s = _session(a, t)
    tmpl = CombatTemplate.default_6e_superheroic()

    s, r1 = resolve_attack_in_session(s, _attack(a, t, dice=[3] * 8), tmpl)
    after_first = s.combatants["target"].current_stun

    # Second attack aims at the SAME stale handle `t` the caller still holds.
    s, r2 = resolve_attack_in_session(s, _attack(a, t, dice=[3] * 8), tmpl)

    assert after_first == 40 - r1.stun_dealt
    assert s.combatants["target"].current_stun == after_first - r2.stun_dealt


def test_folds_onto_the_session_combatant_not_the_callers_handle():
    """The caller's ``attack.target`` may be a stale copy taken before an
    earlier exchange. Damage must land on whatever the session currently
    holds for that id, or every hit after the first is computed against a
    combatant that never took the previous one."""
    a, t = _attacker(), _target(stun=40)
    s = _session(a, t)
    tmpl = CombatTemplate.default_6e_superheroic()

    s, r1 = resolve_attack_in_session(s, _attack(a, t, dice=[3] * 8), tmpl)
    stale = t                                    # still reads 40 STUN
    assert stale.current_stun == 40
    s, r2 = resolve_attack_in_session(s, _attack(a, stale, dice=[3] * 8), tmpl)

    assert s.combatants["target"].current_stun == 40 - r1.stun_dealt - r2.stun_dealt


# ---- A miss changes nothing ----

def test_a_miss_applies_no_damage():
    a = _attacker()
    t = synthetic_combatant(
        id="target", name="Target", ocv=6, dcv=99, omcv=3, dmcv=99,
        spd=3, dex=10, ego=10, str_=10, con=15, pre=10, rec=5,
        pd=0, ed=0, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=40, max_body=15, max_end=30,
        current_stun=40, current_body=15, current_end=30,
    )
    s = _session(a, t)
    s2, result = resolve_attack_in_session(
        s,
        AttackInput(
            attacker=a, target=t, power=a.attacks[0],
            distance_m=0, aim=None,
            dice=DiceValues(to_hit=[6, 6, 6], damage=[6] * 8),
        ),
        CombatTemplate.default_6e_superheroic(),
    )
    assert result.hit is False
    assert s2.combatants["target"].current_stun == 40
    assert s2.combatants["target"].current_body == 15


# ---- KO falls out for free ----

def test_target_is_ko_once_applied_stun_reaches_zero():
    """``Stunnable.is_ko`` is ``current_stun <= 0``. Once damage is applied
    the property is simply true — no KO event has to be emitted for it."""
    a, t = _attacker(), _target(stun=4)
    s = _session(a, t)
    s2, result = resolve_attack_in_session(
        s, _attack(a, t, dice=[6] * 8), CombatTemplate.default_6e_superheroic(),
    )
    assert result.stun_dealt > 4
    assert s2.combatants["target"].is_ko is True
    assert s2.combatants["target"].current_stun < 0, "STUN must not clamp at 0"


# ---- An unknown target is a caller bug, not a silent no-op ----

def test_target_absent_from_session_raises():
    a, t = _attacker(), _target()
    s = _session(a)                       # target never added
    with pytest.raises(KeyError, match="target"):
        resolve_attack_in_session(
            s, _attack(a, t, dice=[3] * 8),
            CombatTemplate.default_6e_superheroic(),
        )


# ---- The event log still says exactly what it said before ----

def test_the_recorded_payload_is_unchanged():
    a, t = _attacker(), _target()
    s = _session(a, t)
    s2, result = resolve_attack_in_session(
        s, _attack(a, t, dice=[3] * 8), CombatTemplate.default_6e_superheroic(),
    )
    payload = s2.event_log[-1].result_payload
    assert payload["stun_dealt"] == result.stun_dealt
    assert payload["body_dealt"] == result.body_dealt
    assert payload["hit"] is result.hit
    assert payload["target_id"] == "target"


# ---- Mental Blast, the one attack family the wrapper covers separately ----

def test_mental_blast_applies_stun_and_no_body():
    a, t = _attacker(), _target(stun=40, body=15)
    s = _session(a, t)
    s2, result = resolve_mental_blast_in_session(s, a, t, [4, 4, 4, 4])
    assert result.stun_dealt == 16
    assert s2.combatants["target"].current_stun == 40 - 16
    assert s2.combatants["target"].current_body == 15, "6E1 p.249: STUN only"


def test_mental_blast_target_absent_from_session_raises():
    a, t = _attacker(), _target()
    s = _session(a)
    with pytest.raises(KeyError, match="target"):
        resolve_mental_blast_in_session(s, a, t, [4, 4, 4, 4])
