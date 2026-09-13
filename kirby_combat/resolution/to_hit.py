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
    if getattr(attack.power, "no_range_modifier", False):
        # 6E1 p.346. The audit must say WHY it is zero: a zero that was
        # bought with an Advantage and a zero that means "nobody measured"
        # are different facts, and for a long time this line only ever
        # reported the second one.
        audit.append("Range penalty: 0 (No Range Modifier)")
    elif attack.power.range_m is not None and attack.distance_m is not None:
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
    # A GRAB IN PROGRESS (Western Hero p.104): both men are 1/2 DCV, both
    # are 1/2 OCV against anybody else, and the victim is -3 OCV against
    # his grabber (that part arrives as an `ocv_modifier` delta). Applied
    # through `apply_cv_factor` -- 6E2 p.39's halving -- exactly as the
    # Surprise DCV halving above is, so the two cannot come to disagree
    # about what halving a CV means.
    if attack.grab_ocv_factor != 1.0:
        from kirby_combat.cv_modifiers import apply_cv_factor

        base_ocv = apply_cv_factor(base_ocv, attack.grab_ocv_factor)
        audit.append(f"Grab: OCV x{attack.grab_ocv_factor} -> {base_ocv}")
    # FIRING INTO MELEE (6E2 p.45): the other bodies are Behind Cover, so
    # the shot takes their OCV penalty. A DELTA, not a factor -- the page
    # treats it as an ordinary Behind Cover modifier, and the same
    # paragraph's example prices half-cover at -2 OCV.
    melee_cover_ocv = int(getattr(attack, "melee_cover_ocv", 0) or 0)
    if melee_cover_ocv:
        audit.append(
            f"Firing into melee: {melee_cover_ocv:+d} OCV for the other "
            f"bodies (6E2 p45)")

    effective_ocv = (base_ocv + ocv_mod + rng_penalty + csl_bonus
                     + hl_penalty + melee_cover_ocv)
    audit.append(
        f"Effective OCV: {base_ocv} {ocv_mod:+d} (mod) {rng_penalty:+d} (range)"
        f" +{csl_bonus} (CSL) {hl_penalty:+d} (location) = {effective_ocv}"
    )

    # ------------------------------------------------------------------
    # 7. Effective DCV
    # ------------------------------------------------------------------
    base_dcv = attack.target.dcv
    effective_dcv = base_dcv + attack.dcv_modifier
    # A GRAB IN PROGRESS halves the DCV of BOTH men (Western Hero p.104).
    # Placed here and not with the OCV half above because `effective_dcv`
    # is bound on this line -- the first draft halved it before it
    # existed and raised UnboundLocalError on the first shot fired.
    if attack.grab_dcv_factor != 1.0:
        from kirby_combat.cv_modifiers import apply_cv_factor

        effective_dcv = apply_cv_factor(effective_dcv, attack.grab_dcv_factor)
        audit.append(f"Grab: DCV x{attack.grab_dcv_factor} -> {effective_dcv}")

    dcv_mod = attack.dcv_modifier
    if dcv_mod != 0:
        audit.append(
            f"Effective DCV: {base_dcv} {dcv_mod:+d} (modifier) = {effective_dcv}"
        )
    else:
        audit.append(f"Effective DCV: {effective_dcv}")

    # 6E2 p.52. Surprised is 1/2 DCV whether the target was in combat or
    # out of it -- only the STUN doubling and the Placed Shot halving
    # depend on which. Applied to the MODIFIED DCV rather than the base,
    # so a Surprised man who is also prone is halved once from where the
    # other modifiers left him rather than from an untouched 8.
    surprise = getattr(attack, "surprise", None)
    if surprise is not None and surprise:
        from kirby_combat.cv_modifiers import apply_cv_factor

        # ASK THE ENGINE. `apply_cv_factor` is 6E2 p.39's halving, already
        # grounded and already sign-aware: it rounds a positive CV in the
        # character's favour (5 -> 3, not 2) and makes a NEGATIVE CV worse
        # rather than better. A bare `int(dcv * 0.5)` here would have been
        # a second, quietly different halving living next to the first.
        before = effective_dcv
        effective_dcv = apply_cv_factor(effective_dcv, surprise.dcv_factor)
        audit.append(f"{surprise}: DCV {before} -> {effective_dcv}")

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
    # Margin is whole-valued by construction, but arrives as a float
    # when OCV/DCV flow from canon HDC imports (the cost engine's
    # characteristic_value() returns float). Normalize once so
    # ToHitResult.margin honours its int annotation and the audit's
    # {:+d} format works for either input shape.
    margin = int(target_number - roll)
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
