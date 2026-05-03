"""Tests for Damage Reduction + Damage Negation per HERO 6E1 p185.

DR rules:
  - % cut applied AFTER subtractive defenses
  - Class-split (Physical / Energy / Mental)
  - Resistant DR works on Killing too; Normal DR doesn't
  - Multiple DR don't stack — pick max (6E1 p185)

DN rules:
  - DC subtraction applied BEFORE the damage roll
  - Class-split
  - 1 DC = 1d6 normal / ½d6 killing
  - Stacks additively
"""
from __future__ import annotations

import pytest

from kirby_combat.actions import resolve_attack
from kirby_combat.models import (
    AttackInput, AttackPower, Combatant, DefenseItem, DiceValues,
)
from kirby_combat.template import CombatTemplate


def _attacker(*, ocv=10, str_=20, name="atk"):
    return Combatant(
        id="atk", name=name, ocv=ocv, dcv=10, omcv=3, dmcv=3,
        spd=4, dex=10, ego=10, str_=str_, con=10, pre=10, rec=5,
        pd=10, ed=10, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=30, max_body=10, max_end=50,
        current_stun=30, current_body=10, current_end=50,
        knockback_resistance=0,
        attacks=[], defenses=[],
    )


def _defender(*, pd=10, ed=10, rpd=0, red=0, defenses=None):
    return Combatant(
        id="def", name="def", ocv=5, dcv=5, omcv=3, dmcv=3,
        spd=4, dex=10, ego=10, str_=10, con=10, pre=10, rec=5,
        pd=pd, ed=ed, rpd=rpd, red=red, md=0, power_defense=0, flash_defense=0,
        max_stun=30, max_body=10, max_end=50,
        current_stun=30, current_body=10, current_end=50,
        knockback_resistance=0,
        attacks=[], defenses=defenses or [],
    )


def _eb(dice=6):
    return AttackPower(
        xmlid="ENERGYBLAST", name="Bolt", damage_dice=dice,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="ed", range_m=60.0,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
    )


def _hka(dice=2):
    return AttackPower(
        xmlid="HKA", name="Claws", damage_dice=dice,
        half_die=False, plus_one=False,
        damage_type="killing", defense_type="pd", range_m=0.0,
        uses_str=True, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
    )


def _resolve(atk, defender, power, *, damage_dice, stun_mult=2):
    """Drive resolve_attack with a deterministic dice pool."""
    full = power.damage_dice
    dv = DiceValues(
        to_hit=[1, 1, 1],  # 3 — auto-hit
        damage=damage_dice or [4] * full,
        hit_location=[],
        stun_multiplier=[stun_mult] if power.damage_type == "killing" else [],
        knockback=[3, 3],
    )
    ai = AttackInput(
        attacker=atk, target=defender, power=power,
        distance_m=0 if power.range_m == 0 else 6.0,
        aim=None, dice=dv,
        ocv_modifier=0, dcv_modifier=0, dc_modifier=0,
    )
    return resolve_attack(ai, CombatTemplate(name="t"))


# ── Damage Reduction ──────────────────────────────────────────────────────
def test_dr_25_resistant_energy_blocks_quarter_of_eb_damage() -> None:
    """6d6 EB → all 4s = 24 STUN, 6 BODY. ED 10 absorbs 10 STUN/10 BODY:
    14 STUN / 0 BODY through. Then 25% Resistant Energy DR cuts 25%:
    STUN 14 → 10 (int truncate)."""
    dr = DefenseItem(
        name="Body of Air", damage_reduction_pct=25,
        damage_class="energy", dr_resistant=True,
    )
    atk = _attacker()
    deft = _defender(ed=10, defenses=[dr])
    r = _resolve(atk, deft, _eb(dice=6), damage_dice=[4] * 6)
    assert r.stun_dealt == 10  # 14 * 0.75 = 10.5 → 10
    assert r.body_dealt == 0


def test_dr_50_normal_does_not_apply_to_killing() -> None:
    """50% Normal Physical DR. Vs HKA (killing) — should NOT apply.
    1d6 HKA, BODY=4, stun-mult 2 → STUN 8. rPD 0 → STUN 8/BODY 4 through.
    Without DR firing, those numbers persist."""
    dr = DefenseItem(
        name="Tough", damage_reduction_pct=50,
        damage_class="physical", dr_resistant=False,
    )
    deft = _defender(pd=10, rpd=0, defenses=[dr])
    r = _resolve(_attacker(), deft, _hka(dice=1), damage_dice=[4], stun_mult=2)
    # Killing vs PD 10/rPD 0: total_def=10 stops STUN, rPD 0 stops BODY.
    # STUN 8 - 10 = 0 (clamp), BODY 4 - 0 = 4. DR doesn't apply.
    assert r.body_dealt == 4
    assert r.stun_dealt == 0


def test_dr_75_resistant_physical_cuts_killing_75pct() -> None:
    """75% Resistant Physical DR + 1d6 HKA, BODY=6 (rolled 6),
    stun-mult-die=4 (½d6 mult of 2 per 6E table) → STUN 12.
    rPD 0 → STUN 12/BODY 6 through. Resistant DR applies to killing:
    STUN 12 * 0.25 = 3, BODY 6 * 0.25 = 1."""
    dr = DefenseItem(
        name="Stone Skin", damage_reduction_pct=75,
        damage_class="physical", dr_resistant=True,
    )
    deft = _defender(pd=0, rpd=0, defenses=[dr])
    # stun_mult=4 → engine ½d6 table → mult=2
    r = _resolve(_attacker(), deft, _hka(dice=1), damage_dice=[6], stun_mult=4)
    assert r.body_dealt == 1
    assert r.stun_dealt == 3


def test_dr_class_mismatch_does_not_apply() -> None:
    """Resistant Energy DR vs a Physical (HKA) attack: doesn't fire.
    Defender has pd=0 (override default 10), rpd=0. Killing attack
    uses total_defense for STUN and resistant_defense for BODY:
    both are 0 → all damage through, then DR doesn't apply (class
    mismatch)."""
    dr = DefenseItem(
        name="Energy Shield", damage_reduction_pct=75,
        damage_class="energy", dr_resistant=True,
    )
    deft = _defender(pd=0, rpd=0, defenses=[dr])
    # stun_mult_die=4 → engine mult=2 → STUN 12, BODY 6
    r = _resolve(_attacker(), deft, _hka(dice=1), damage_dice=[6], stun_mult=4)
    assert r.body_dealt == 6
    assert r.stun_dealt == 12


def test_dr_does_not_stack_picks_max() -> None:
    """Two Resistant DR powers (25% + 50%, same class) → engine picks
    max(50%) per 6E1 p185 — no stacking."""
    dr1 = DefenseItem(
        name="DR-A", damage_reduction_pct=25,
        damage_class="energy", dr_resistant=True,
    )
    dr2 = DefenseItem(
        name="DR-B", damage_reduction_pct=50,
        damage_class="energy", dr_resistant=True,
    )
    deft = _defender(ed=0, defenses=[dr1, dr2])
    # 6d6 EB, all 4 = 24 STUN, 6 BODY. ED 0 → all through.
    # 50% DR (the max): 24*0.5=12, 6*0.5=3.
    r = _resolve(_attacker(), deft, _eb(dice=6), damage_dice=[4] * 6)
    assert r.stun_dealt == 12
    assert r.body_dealt == 3


# ── Damage Negation ───────────────────────────────────────────────────────
def test_dn_2_dcs_subtracts_2d6_from_normal_attack() -> None:
    """6d6 EB has 6 DCs. DN 2 (energy) → 4d6 EB. All 4s = 16 STUN/4 BODY.
    ED 10 absorbs 10 each → 6 STUN, 0 BODY."""
    dn = DefenseItem(
        name="Negate Energy", damage_negation=2,
        damage_class="energy", dr_resistant=True,
    )
    deft = _defender(ed=10, defenses=[dn])
    r = _resolve(_attacker(), deft, _eb(dice=6), damage_dice=[4] * 4)
    # Engine pre-cuts to 4d6, then rolls; we supplied 4 dice all 4s.
    # 16 - 10 = 6 STUN. 4 - 10 = 0 BODY (clamped).
    assert r.stun_dealt == 6
    assert r.body_dealt == 0


def test_dn_3_dcs_halves_killing_attack() -> None:
    """1d6 HKA = 3 DCs. DN 3 (physical) → 0d6 (zeroed out).
    Damage roll yields 0 BODY 0 STUN."""
    dn = DefenseItem(
        name="Stone Negation", damage_negation=3,
        damage_class="physical", dr_resistant=True,
    )
    deft = _defender(rpd=0, defenses=[dn])
    r = _resolve(_attacker(), deft, _hka(dice=1), damage_dice=[], stun_mult=2)
    assert r.stun_dealt == 0
    assert r.body_dealt == 0


def test_dn_class_mismatch_does_not_apply() -> None:
    """DN Physical vs Energy attack: no effect. 6d6 EB unchanged → 24/6.
    ED 10 → 14 STUN / 0 BODY."""
    dn = DefenseItem(
        name="Physical Negation", damage_negation=4,
        damage_class="physical", dr_resistant=True,
    )
    deft = _defender(ed=10, defenses=[dn])
    r = _resolve(_attacker(), deft, _eb(dice=6), damage_dice=[4] * 6)
    assert r.stun_dealt == 14
    assert r.body_dealt == 0


def test_dn_stacks_additively() -> None:
    """Two DN powers, same class — sum the DCs (DN stacks per 6E1 p185
    where DR doesn't). 1+2 = 3 DCs subtracted."""
    dn1 = DefenseItem(name="A", damage_negation=1, damage_class="energy")
    dn2 = DefenseItem(name="B", damage_negation=2, damage_class="energy")
    deft = _defender(ed=0, defenses=[dn1, dn2])
    # 6d6 EB - 3 DC = 3d6. All 4s = 12 STUN, 3 BODY through ED 0.
    r = _resolve(_attacker(), deft, _eb(dice=6), damage_dice=[4] * 3)
    assert r.stun_dealt == 12
    assert r.body_dealt == 3


# ── Rule-order regression gate ────────────────────────────────────────────
def test_rule_order_defenses_subtract_FIRST_then_dr_multiplies() -> None:
    """Rule order is explicit per HERO 6E1 p185 (USING DAMAGE NEGATION):

        "The effect of the attack is then rolled normally and the
         character applies his regular defenses, Damage Reduction, and
         any other defensive abilities."

    Order: defenses (PD/ED subtraction) FIRST, then Damage Reduction
    (% multiplier) on the remainder.

    Dice are rigged to produce strongly divergent results between the
    two orderings, so flipping the order in the resolver — even
    accidentally — fails the test loudly.

    Setup: 6d6 EB damage rolled all 5s = 30 STUN, 6 BODY (each 5 = 1
    BODY in HERO 6E normal-damage tables). Defender has 16 ED + 50%
    Resistant Energy DR.

    DEFENSES FIRST (correct, 6E1 p185):
        STUN: 30 − 16 = 14, then × 0.5 = 7 → stun_dealt = 7
        BODY:  6 − 16 = 0 (clamped), then × 0.5 = 0 → body_dealt = 0

    DR FIRST (wrong):
        STUN: 30 × 0.5 = 15, then − 16 = 0 (clamped) → stun_dealt = 0
        BODY:  6 × 0.5 = 3, then − 16 = 0 (clamped) → body_dealt = 0

    The test asserts stun_dealt == 7 — the wrong order produces 0,
    so any future regression where DR is applied before subtractive
    defenses fails this assertion immediately.
    """
    dr = DefenseItem(
        name="Energy Damper", damage_reduction_pct=50,
        damage_class="energy", dr_resistant=True,
    )
    deft = _defender(ed=16, defenses=[dr])
    # 6d6 all 5s: each 5 contributes +5 STUN, +1 BODY → 30 STUN, 6 BODY
    r = _resolve(_attacker(), deft, _eb(dice=6), damage_dice=[5] * 6)
    assert r.stun_dealt == 7, (
        f"Rule order broken: expected 7 STUN (defenses-first: 30-16=14, "
        f"14*0.5=7); got {r.stun_dealt}. If DR fires before defense "
        f"subtraction, the result would be 0 STUN (30*0.5=15, 15-16=0 "
        f"clamped). 6E1 p185 explicitly says defenses FIRST, then DR."
    )
    assert r.body_dealt == 0


def test_dn_and_dr_compose_dn_first_then_dr() -> None:
    """DN 1 (energy) + 50% Resistant Energy DR.
    6d6 EB - 1 DC = 5d6. All 4s = 20 STUN/5 BODY. ED 10 → 10 STUN/0 BODY.
    50% DR → 5 STUN/0 BODY."""
    dn = DefenseItem(name="DN", damage_negation=1, damage_class="energy")
    dr = DefenseItem(
        name="DR", damage_reduction_pct=50,
        damage_class="energy", dr_resistant=True,
    )
    deft = _defender(ed=10, defenses=[dn, dr])
    r = _resolve(_attacker(), deft, _eb(dice=6), damage_dice=[4] * 5)
    assert r.stun_dealt == 5
    assert r.body_dealt == 0
