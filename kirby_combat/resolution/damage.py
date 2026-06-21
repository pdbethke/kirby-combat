"""HERO System 6E damage calculation.

compute_damage(power, dice, template, hit_location=None) -> DamageResult

Normal damage
-------------
- STUN = sum of all full dice values
- BODY per full die: 1 → 0, 2-5 → 1, 6 → 2
- Half die (power.half_die=True): consume next dice value as half-die.
    STUN += value // 2
    BODY += 1 if value >= 5 else 0
- Plus one (power.plus_one=True): STUN += 1, no BODY change

Killing damage
--------------
- BODY = sum of all full dice values
    (half_die: BODY += value // 2)
    (plus_one: BODY += 1)
- STUN multiplier (per 6E2 p100 §Killing Damage Attacks):
    If template.killing_stun_mult_fixed is set → use that value.
    Otherwise: roll ½d6 (range 1-3) — caller passes a raw d6 in
    dice.stun_multiplier[0] (1-6) and we map to a half-die value
    via half_die = (raw_d6 + 1) // 2 (round-up halving).
    Final multiplier = base + (half_die - 1) + power.increased_stun_mult,
    minimum 1.
    Per 6E1 p244, Increased STUN Multiplier ADDS to the rolled ½d6.
- STUN = BODY × multiplier  (integer result)
"""
from __future__ import annotations

from kirby_combat.models import AttackPower, DamageResult, DiceValues
from kirby_combat.template import CombatTemplate


# ---------------------------------------------------------------------------
# BODY-per-die table for normal damage
# ---------------------------------------------------------------------------

def _body_for_normal_die(value: int) -> int:
    """Return the BODY contribution of a single normal-damage die face."""
    if value == 1:
        return 0
    if value == 6:
        return 2
    return 1  # 2-5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_damage(
    power: AttackPower,
    dice: DiceValues,
    template: CombatTemplate,
    hit_location: str | None = None,
) -> DamageResult:
    """Compute raw damage from rolled dice, returning a DamageResult.

    Parameters
    ----------
    power:
        The attacking power/weapon (determines damage_type, half_die, plus_one,
        increased_stun_mult).
    dice:
        Raw dice values.  ``dice.damage`` holds the individual die results.
        If ``power.half_die`` is True, the *last* value in ``dice.damage`` is
        treated as the half-die result; the preceding values are full dice.
        ``dice.stun_multiplier`` is consumed for killing attacks (first element).
    template:
        Campaign template governing the stun-multiplier rules.
    hit_location:
        Optional hit location string (reserved for future location modifiers).

    Returns
    -------
    DamageResult
    """
    audit: list[str] = []
    damage_values = list(dice.damage)

    # ------------------------------------------------------------------
    # Split full dice vs half-die
    # ------------------------------------------------------------------
    if power.half_die and damage_values:
        half_die_value = damage_values[-1]
        full_dice = damage_values[:-1]
        audit.append(
            f"Half-die enabled: full dice={full_dice}, half-die raw value={half_die_value}"
        )
    else:
        half_die_value = None
        full_dice = damage_values

    audit.append(f"Full dice: {full_dice}")

    # ------------------------------------------------------------------
    # Delegate to damage-type-specific calculation
    # ------------------------------------------------------------------
    if power.damage_type == "killing":
        stun, body, stun_mult = _compute_killing(
            power, full_dice, half_die_value, dice, template, audit
        )
    else:
        # Treat anything that is not "killing" as normal damage
        stun, body, stun_mult = _compute_normal(
            power, full_dice, half_die_value, audit
        )

    audit.append(f"Final → STUN={stun}, BODY={body}")

    return DamageResult(
        stun=stun,
        body=body,
        dice_values=dice,
        damage_type=power.damage_type,
        hit_location=hit_location or "",
        stun_multiplier=stun_mult,
        body_multiplier=1.0,
        is_partial=False,
        audit=audit,
    )


# ---------------------------------------------------------------------------
# Normal damage
# ---------------------------------------------------------------------------

def _compute_normal(
    power: AttackPower,
    full_dice: list[int],
    half_die_value: int | None,
    audit: list[str],
) -> tuple[int, int, int]:
    """Return (stun, body, stun_multiplier=1) for a normal damage roll."""
    stun = sum(full_dice)
    body = sum(_body_for_normal_die(v) for v in full_dice)
    audit.append(f"Normal STUN from full dice: {stun}")
    audit.append(f"Normal BODY from full dice: {body}")

    # Half-die contribution
    if half_die_value is not None:
        hd_stun = half_die_value // 2
        hd_body = 1 if half_die_value >= 5 else 0
        stun += hd_stun
        body += hd_body
        audit.append(
            f"Half-die value={half_die_value}: STUN +{hd_stun}, BODY +{hd_body}"
        )

    # Plus-one contribution (STUN only, no BODY)
    if power.plus_one:
        stun += 1
        audit.append("Plus-one: STUN +1, BODY +0")

    return stun, body, 1


# ---------------------------------------------------------------------------
# Killing damage
# ---------------------------------------------------------------------------

def _compute_killing(
    power: AttackPower,
    full_dice: list[int],
    half_die_value: int | None,
    dice: DiceValues,
    template: CombatTemplate,
    audit: list[str],
) -> tuple[int, int, int]:
    """Return (stun, body, stun_multiplier) for a killing damage roll."""
    # BODY = sum of full dice (raw face values, not normal-damage counting)
    body = sum(full_dice)
    audit.append(f"Killing BODY from full dice: {body}")

    # Half-die adds value // 2 to BODY
    if half_die_value is not None:
        hd_body = half_die_value // 2
        body += hd_body
        audit.append(f"Half-die value={half_die_value}: BODY +{hd_body}")

    # Plus-one adds 1 to BODY
    if power.plus_one:
        body += 1
        audit.append("Plus-one: BODY +1")

    # ------------------------------------------------------------------
    # STUN multiplier
    # ------------------------------------------------------------------
    if template.killing_stun_mult_fixed is not None:
        stun_mult = template.killing_stun_mult_fixed
        audit.append(f"Killing STUN multiplier: fixed={stun_mult} (from template)")
    else:
        # Per 6E2 p100: roll ½d6 (range 1-3). Caller passes a raw d6 (1-6);
        # we map to a half-die via round-up halving: (n+1)//2 → 1,1,2,2,3,3.
        stun_mult_die = dice.stun_multiplier[0] if dice.stun_multiplier else 1
        half_die = (stun_mult_die + 1) // 2
        base = template.killing_stun_mult_base
        inc = power.increased_stun_mult or 0
        raw_mult = base + (half_die - 1) + inc
        stun_mult = max(1, raw_mult)
        audit.append(
            f"Killing STUN multiplier: ½d6 from die={stun_mult_die} → half_die={half_die}, "
            f"base={base}, +increased={inc} → final={stun_mult}"
        )

    stun = body * stun_mult
    audit.append(f"Killing STUN: {body} BODY × {stun_mult} multiplier = {stun}")

    return stun, body, stun_mult


# ---------------------------------------------------------------------------
# Variable Multipower slot dice scaling (6E1 p405)
# ---------------------------------------------------------------------------

def scale_variable_slot_dice(
    *,
    base_dice: int,
    active_points: int,
    assigned_points: int,
) -> int:
    """Scale a variable Multipower slot's dice by the fraction of reserve assigned.

    6E1 p405: a variable slot that is assigned fewer reserve points than its
    Active Point cost has its dice reduced proportionally (floor to whole dice).
    Fixed slots always run at full power; this helper is only called for
    variable-type slots.

    Parameters
    ----------
    base_dice:
        The slot's full-power dice count (at full active_points).
    active_points:
        The slot's Active Point cost (cost at full power).  If 0 or unknown,
        the function returns base_dice unchanged — safe default.
    assigned_points:
        Reserve points currently allocated to this slot.  If >= active_points
        the slot runs at full power.

    Returns
    -------
    int
        Scaled dice count, floored to the nearest whole die.  Minimum 0.
    """
    if not active_points or assigned_points >= active_points:
        return base_dice
    return max(0, int(base_dice * assigned_points / active_points))

    return stun, body, stun_mult
