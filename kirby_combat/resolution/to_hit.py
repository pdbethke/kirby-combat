"""HERO System 6E to-hit resolution.

Formula: Roll 3d6 <= (OCV + 11 - DCV) to hit.
"""
from __future__ import annotations

from kirby_combat.models import AttackInput, ToHitResult
from kirby_combat.tables import HIT_LOCATIONS, range_penalty as _range_penalty
from kirby_combat.template import CombatTemplate

_DEFAULT_ROLL = 11


def resolve_to_hit(attack: AttackInput, template: CombatTemplate) -> ToHitResult:
    """Compute the to-hit result for a single attack.

    Parameters
    ----------
    attack:
        All inputs for this attack (attacker, target, power, dice, modifiers).
    template:
        Campaign-level settings (e.g. use_hit_locations).

    Returns
    -------
    ToHitResult
        Fully populated result including hit/miss, margin, effective stats,
        and a human-readable audit trail.
    """
    audit: list[str] = []

    # ------------------------------------------------------------------
    # 1. Base OCV from attacker
    # ------------------------------------------------------------------
    base_ocv = attack.attacker.ocv
    audit.append(f"Base OCV: {base_ocv}")

    # ------------------------------------------------------------------
    # 2. OCV modifier (maneuver / situational)
    # ------------------------------------------------------------------
    ocv_mod = attack.ocv_modifier
    if ocv_mod != 0:
        audit.append(f"OCV modifier (maneuver/situational): {ocv_mod:+d}")

    # ------------------------------------------------------------------
    # 3. Range penalty
    #    Applied only if the power has a range AND distance is provided.
    # ------------------------------------------------------------------
    rng_penalty = 0
    if attack.power.range_m is not None and attack.distance_m is not None:
        rng_penalty = _range_penalty(attack.distance_m)
        audit.append(
            f"Range penalty ({attack.distance_m}m): {rng_penalty:+d}"
        )
    else:
        audit.append("Range penalty: 0 (HTH or distance not specified)")

    # ------------------------------------------------------------------
    # 4. Combat Skill Level bonus
    #    Sum levels for CSLs allocated to "ocv" or "any".
    # ------------------------------------------------------------------
    csl_bonus = sum(
        csl.levels
        for csl in attack.attacker.csls
        if csl.applies_to in ("ocv", "any")
    )
    if csl_bonus != 0:
        audit.append(f"CSL bonus (ocv/any): +{csl_bonus}")

    # ------------------------------------------------------------------
    # 5. Hit location penalty
    #    Applied only if aim is set AND template.use_hit_locations is True.
    # ------------------------------------------------------------------
    hl_penalty = 0
    if attack.aim is not None and template.use_hit_locations:
        loc = HIT_LOCATIONS.get(attack.aim)
        if loc is not None:
            hl_penalty = loc["ocvMod"]
            audit.append(
                f"Hit location aim ({attack.aim}): {hl_penalty:+d} OCV"
            )
        else:
            audit.append(f"Hit location aim ({attack.aim}): unknown location, no penalty")
    else:
        if attack.aim is not None and not template.use_hit_locations:
            audit.append("Hit location penalty: 0 (use_hit_locations is OFF in template)")
        else:
            audit.append("Hit location penalty: 0 (no aim specified)")

    # ------------------------------------------------------------------
    # 6. Effective OCV
    # ------------------------------------------------------------------
    effective_ocv = base_ocv + ocv_mod + rng_penalty + csl_bonus + hl_penalty
    audit.append(
        f"Effective OCV: {base_ocv} {ocv_mod:+d} (mod) {rng_penalty:+d} (range)"
        f" +{csl_bonus} (CSL) {hl_penalty:+d} (location) = {effective_ocv}"
    )

    # ------------------------------------------------------------------
    # 7. Effective DCV
    # ------------------------------------------------------------------
    base_dcv = attack.target.dcv
    effective_dcv = base_dcv + attack.dcv_modifier
    dcv_mod = attack.dcv_modifier
    if dcv_mod != 0:
        audit.append(
            f"Effective DCV: {base_dcv} {dcv_mod:+d} (modifier) = {effective_dcv}"
        )
    else:
        audit.append(f"Effective DCV: {effective_dcv}")

    # ------------------------------------------------------------------
    # 8. Target number
    # ------------------------------------------------------------------
    target_number = effective_ocv + 11 - effective_dcv
    audit.append(
        f"Target number: {effective_ocv} + 11 - {effective_dcv} = {target_number}"
    )

    # ------------------------------------------------------------------
    # 9. Roll
    #    Use first three dice from dice.to_hit; default to 11 if empty.
    # ------------------------------------------------------------------
    dice = attack.dice.to_hit[:3]
    if dice:
        roll = sum(dice)
        audit.append(f"Roll: {dice} = {roll}")
    else:
        roll = _DEFAULT_ROLL
        audit.append(f"Roll: (no dice provided, defaulting to {_DEFAULT_ROLL})")

    # ------------------------------------------------------------------
    # 10. Hit / miss
    # ------------------------------------------------------------------
    hit = roll <= target_number
    margin = target_number - roll
    outcome = "HIT" if hit else "MISS"
    audit.append(
        f"Result: {roll} vs {target_number} — {outcome}"
        f" (margin: {margin:+d})"
    )

    return ToHitResult(
        hit=hit,
        roll=roll,
        target_number=target_number,
        margin=margin,
        effective_ocv=effective_ocv,
        effective_dcv=effective_dcv,
        range_penalty=rng_penalty,
        hit_location_penalty=hl_penalty,
        csl_bonus=csl_bonus,
        audit=audit,
    )
