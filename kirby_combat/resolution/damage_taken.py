"""What one hit does to a man: the damage step of the attack door.

LIFTED FROM `actions/base.py` (2026-11-10), verbatim but for the names its
inputs arrive under, so the resolver and anything that prices an attack
before it is rolled (`kirby_combat.odds`) ask ONE function and cannot
disagree. kirby-ai's EV seat assembled its own copy from the pieces and
missed the Penetrating minimum; a rule with two homes drifts.

Defense (6E1 p.185: Damage Negation before the roll), the damage, the
defenses (Hit Location multipliers in the order the book gives), the shot
that found the cover, AVAD's STUN only, Damage Reduction, Penetrating's
minimum, a save that halves the damage taken, and the STUN a BODY costs.
WHERE it landed --- the Hit Location roll and whether it found the cover ---
is the caller's (it needs the attack's aim and the cover it was rolled
against), and arrives as ``location`` and ``blocked_by_cover``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kirby_combat.models import DamageResult, DefenseProfile, DiceValues
from kirby_combat.resolution.damage import compute_damage, stun_for_body_taken
from kirby_combat.resolution.defense import compute_defense
from kirby_combat.resolution.hit_location import killing_damage, normal_damage


@dataclass(frozen=True)
class DamageTaken:
    """What got through, and what it was worked out from."""

    stun: int
    body: int
    damage: DamageResult
    defense: DefenseProfile
    #: The attack as it landed: Damage Negation and a DC penalty take dice
    #: off it before the roll (6E1 p.185), and Knockback and status read it.
    power: Any
    dice: DiceValues
    audit: tuple[str, ...]


def damage_taken(power, target, dice, template, *, aim=None, location=None,
                 blocked_by_cover: bool = False, surprise=None,
                 dc_modifier: int = 0,
                 damage_taken_factor: float = 1.0) -> DamageTaken:
    """The STUN and BODY one hit puts on ``target``. See the module."""
    audit_trail: list[str] = []
    # ------------------------------------------------------------------
    # 2. Defense (computed first so we can apply Damage Negation
    #    pre-damage-roll, per 6E1 p185 "uSING DAmAGE NEGATION":
    #    "A character applies his Damage Negation to an incoming
    #    attack before applying his other defenses. Before the
    #    attacker makes the Effect Roll for his attack, he reduces
    #    it to account for the Damage Negation.")
    # ------------------------------------------------------------------
    defense = compute_defense(target, power)
    audit_trail.extend(defense.audit)

    # ------------------------------------------------------------------
    # 3. Damage Negation: trim DCs from the attack BEFORE the roll.
    # ------------------------------------------------------------------
    effective_power = power
    effective_dice = dice
    # AND THE ATTACKER'S OWN DC PENALTY (6E2 p.48-49's -2 DCs from a
    # difficult climb, `climbing_state`), trimmed the same way. A DC
    # BONUS on this channel has no reader: raise rather than ignore it.
    if dc_modifier > 0:
        raise ValueError(
            f"AttackInput.dc_modifier {dc_modifier} is a bonus; "
            "only a DC penalty is read here")
    if defense.damage_negation > 0 or dc_modifier < 0:
        from dataclasses import replace as _replace
        dcs_remove = defense.damage_negation - int(dc_modifier)
        new_full = power.damage_dice
        new_half = power.half_die
        if power.damage_type == "killing":
            # 1 DC = ½d6 = 1 half-die step
            steps = new_full * 2 + (1 if new_half else 0)
            steps = max(0, steps - dcs_remove)
            new_full = steps // 2
            new_half = bool(steps % 2)
        else:
            # 1 DC = 1d6 normal
            new_full = max(0, new_full - dcs_remove)
        effective_power = _replace(
            power, damage_dice=new_full, half_die=new_half,
        )
        # Also truncate the rolled dice — compute_damage reads
        # dice.damage, not power.damage_dice. Keep n_full + (1 if
        # half_die) leading dice; rest are discarded.
        n_keep = new_full + (1 if new_half else 0)
        effective_dice = _replace(
            dice, damage=list(dice.damage[:n_keep]),
        )
        audit_trail.append(
            f"Damage Negation / DC penalty applied pre-roll: -{dcs_remove} DC "
            f"({power.damage_dice}{'+½' if power.half_die else ''}d6 → "
            f"{new_full}{'+½' if new_half else ''}d6 {power.damage_type})"
        )

    # ------------------------------------------------------------------
    # 4. Damage
    # ------------------------------------------------------------------
    damage = compute_damage(
        effective_power, effective_dice, template, hit_location=aim,
    )
    audit_trail.extend(damage.audit)

    # 6E2 p.52's doubling for a target Surprised OUT of combat:
    # "Double the STUN damage before applying defenses (and, in
    # campaigns using the Hit Locations rules, before applying the
    # STUN modifier for a location)." It is passed INTO each damage
    # function rather than applied to a result here, because the two
    # damage types put the subtraction in different places and only
    # they know where "before defenses" is.
    surprise = surprise
    surprise_stun_x = surprise.stun_multiplier if surprise else 1

    if location is not None:
        if effective_power.damage_type == "killing":
            stun_dealt, body_dealt = killing_damage(
                damage.body, total_defense=defense.total_defense,
                resistant_defense=defense.resistant_defense,
                effect=location, stun_multiplier=surprise_stun_x,
            )
        else:
            stun_dealt, body_dealt = normal_damage(
                damage.stun, damage.body,
                total_defense=defense.total_defense, effect=location,
                stun_multiplier=surprise_stun_x,
            )
        audit_trail.append(
            f"Hit Location {location.name}: STUNx {location.stun_x}, "
            f"N STUN x{location.normal_stun_x}, BODYx {location.body_x} "
            f"(6E2 p110-111) -> STUN {stun_dealt}, BODY {body_dealt}"
        )
    elif effective_power.damage_type == "killing":
        stun_dealt = max(
            0, damage.stun * surprise_stun_x - defense.total_defense)
        body_dealt = max(0, damage.body - defense.resistant_defense)
    else:
        stun_dealt = max(
            0, damage.stun * surprise_stun_x - defense.total_defense)
        body_dealt = max(0, damage.body - defense.total_defense)

    if surprise_stun_x != 1:
        audit_trail.append(
            f"{surprise}: STUN doubled before defenses (6E2 p52)"
        )

    # THE SHOT WENT INTO THE COVER. Applied after the branches above
    # so the audit still shows what the attack would have done, and
    # before Penetrating, whose minimum is a minimum of damage TO THE
    # TARGET and there is none.
    if blocked_by_cover:
        stun_dealt = 0
        body_dealt = 0

    # AVAD/NND attacks do STUN only (6E1 p328) unless they bought Does BODY (+1).
    if (getattr(effective_power, "avad", False)
            and not getattr(effective_power, "avad_does_body", False)):
        if body_dealt:
            audit_trail.append(
                f"AVAD/NND does STUN only (no Does BODY adder): BODY {body_dealt}→0"
            )
        body_dealt = 0

    audit_trail.append(
        f"Damage after defenses: STUN={stun_dealt}, BODY={body_dealt}"
    )

    # ------------------------------------------------------------------
    # 6. Damage Reduction: % cut applied AFTER subtractive defenses
    #    (6E1 p185 "uSING DAmAGE NEGATION": "The effect of the attack
    #    is then rolled normally and the character applies his
    #    regular defenses, Damage Reduction, and any other
    #    defensive abilities.")
    # ------------------------------------------------------------------
    if defense.damage_reduction_pct > 0:
        mult = (100 - defense.damage_reduction_pct) / 100.0
        stun_after_dr = int(stun_dealt * mult)
        body_after_dr = int(body_dealt * mult)
        audit_trail.append(
            f"Damage Reduction {defense.damage_reduction_pct}%: "
            f"STUN {stun_dealt}→{stun_after_dr}, "
            f"BODY {body_dealt}→{body_after_dr}"
        )
        stun_dealt = stun_after_dr
        body_dealt = body_after_dr

    # PENETRATING (6E1 p.344): a minimum for the roll made --- STUN on a
    # Normal attack, BODY on a Killing one --- replacing a smaller result
    # and never adding to a larger. AFTER Damage Reduction, which
    # "does not affect the minimum damage caused by a Penetrating
    # attack" (p.188; Damage Negation's lost dice already lowered the
    # roll, p.186). Not through the cover: the shot never touched him.
    from kirby_combat.resolution.penetrating import penetrating_minimum

    minimum = penetrating_minimum(effective_power, target, effective_dice.damage)
    if not blocked_by_cover and (minimum.stun > stun_dealt or minimum.body > body_dealt):
        audit_trail.append(
            f"Penetrating minimum (6E1 p344): STUN {stun_dealt}->"
            f"{max(stun_dealt, minimum.stun)}, BODY {body_dealt}->"
            f"{max(body_dealt, minimum.body)}")
        stun_dealt = max(stun_dealt, minimum.stun)
        body_dealt = max(body_dealt, minimum.body)

    # A SAVE THAT HALVES THE DAMAGE TAKEN (6E2 p.85, the Thrown
    # character's Breakfall). After defenses and Damage Reduction,
    # because that is what "taken" means.
    factor = damage_taken_factor
    if factor not in (1.0, 0.5):
        raise ValueError(
            f"damage_taken_factor must be 1.0 or 0.5 (6E2 p.85 halves), "
            f"got {factor!r}")
    if factor == 0.5:
        audit_trail.append(
            f"Damage taken halved (6E2 p85): STUN {stun_dealt}→"
            f"{stun_dealt // 2}, BODY {body_dealt}→{body_dealt // 2}")
        stun_dealt //= 2
        body_dealt //= 2

    # BODY THAT GOT THROUGH COSTS STUN (6E2 p.105), whatever the
    # defenses did to the STUN: a killing attack against a man with no
    # resistant defense took his BODY and left his STUN untouched.
    floored = stun_for_body_taken(stun_dealt, body_dealt)
    if floored != stun_dealt:
        audit_trail.append(
            f"1 STUN per BODY taken (6E2 p105): STUN {stun_dealt}→{floored}"
        )
        stun_dealt = floored

    audit_trail.append(
        f"Damage applied: STUN dealt={stun_dealt}, BODY dealt={body_dealt}"
    )
    return DamageTaken(stun=stun_dealt, body=body_dealt, damage=damage,
                       defense=defense, power=effective_power,
                       dice=effective_dice, audit=tuple(audit_trail))
