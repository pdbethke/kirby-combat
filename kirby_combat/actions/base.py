"""Base attack action with the shared resolution pipeline."""
from __future__ import annotations

from kirby_combat.models import AttackInput, AttackResult, DamageResult, DefenseProfile, KnockbackResult, ToHitResult
from kirby_combat.endurance import end_cost
from kirby_combat.resolution.hit_location import (
    effect_for, exposed_through_cover, killing_damage, location_for_roll,
    normal_damage, uses_hit_locations,
)
from kirby_combat.resolution.damage import compute_damage
from kirby_combat.resolution.defense import compute_defense
from kirby_combat.resolution.knockback import compute_knockback
from kirby_combat.resolution.status import determine_status_changes
from kirby_combat.resolution.to_hit import resolve_to_hit
from kirby_combat.template import CombatTemplate


class AttackAction:
    """Shared attack resolution pipeline.

    Subclasses may override hooks in the future; for Phase 1 all three
    concrete action types (Strike, Ranged, Killing) use this pipeline
    unchanged.
    """

    name: str = "attack"

    def resolve(self, attack: AttackInput, template: CombatTemplate) -> AttackResult:
        """Run the full attack resolution pipeline.

        Steps
        -----
        1. To-hit roll
        2. Damage calculation
        3. Defense aggregation
        4. Apply damage (killing vs normal rules)
        5. Knockback (if enabled and BODY dealt > 0)
        6. Status changes
        7. END cost
        8. Build audit trail
        """
        audit_trail: list[str] = []
        power = attack.power
        target = attack.target

        # ------------------------------------------------------------------
        # 1. To-hit
        # ------------------------------------------------------------------
        to_hit = resolve_to_hit(attack, template)
        audit_trail.extend(to_hit.audit)

        if not to_hit.hit:
            return AttackResult(
                hit=False,
                to_hit=to_hit,
                damage=None,
                defense=None,
                stun_dealt=0,
                body_dealt=0,
                end_spent=end_cost(power),
                knockback=None,
                status_changes=[],
                power_xmlid=power.xmlid,
                audit_trail=audit_trail,
            )

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
        effective_dice = attack.dice
        if defense.damage_negation > 0:
            from dataclasses import replace as _replace
            dcs_remove = defense.damage_negation
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
                attack.dice, damage=list(attack.dice.damage[:n_keep]),
            )
            audit_trail.append(
                f"Damage Negation applied pre-roll: -{dcs_remove} DC "
                f"({power.damage_dice}{'+½' if power.half_die else ''}d6 → "
                f"{new_full}{'+½' if new_half else ''}d6 {power.damage_type})"
            )

        # ------------------------------------------------------------------
        # 4. Damage
        # ------------------------------------------------------------------
        damage = compute_damage(
            effective_power, effective_dice, template, hit_location=attack.aim,
        )
        audit_trail.extend(damage.audit)

        # ------------------------------------------------------------------
        # 5. Apply defenses (subtract PD/ED/rPD/rED)
        # ------------------------------------------------------------------
        # WHERE IT LANDED, WHEN THE CAMPAIGN CARES (6E2 p.110-111).
        # `tables.HIT_LOCATIONS` has carried STUNx / N STUN / BODYx for
        # every body part all along and only `ocvMod` was ever read, so a
        # fighter could aim at the head, pay -8 OCV, hit, and do ordinary
        # damage. Aiming was strictly worse than not aiming.
        #
        # The multipliers do NOT commute with defenses and the book is
        # specific about the order, which is why this goes through
        # `resolution/hit_location.py` rather than a factor applied here:
        # Killing STUN multiplies BEFORE defenses, Normal STUN AFTER, and
        # BODY always after.
        # THE AIM BEATS THE ROLL (6E2 p.111's Placed Shot: the character
        # chose the location, so the dice do not choose it for him).
        # Otherwise the table is rolled, which is step 1 of BOTH damage
        # procedures -- "Roll 3d6 and consult the first two columns" --
        # and is why `DiceValues.hit_location` exists. Nothing wrote it
        # and nothing read it, so a heroic campaign got hit locations only
        # on deliberately aimed shots, which is not the rule.
        location = None
        blocked_by_cover = False
        if uses_hit_locations(template, target):
            location = effect_for(attack.aim, template=template)
            if location is None:
                rolled = sum(attack.dice.hit_location or ())
                # BEHIND SOMETHING, THE HIGH ROLLS HIT IT (6E2 p.45):
                # "any Hit Location roll of 12 or more hits the rock,
                # doing no damage to her". An AIMED shot is exempt --- it
                # chose a location and did not roll one.
                if rolled and not exposed_through_cover(
                        rolled, cover_level=attack.target_cover_level):
                    blocked_by_cover = True
                    audit_trail.append(
                        f"Hit Location roll {rolled} finds the cover, not the "
                        f"target (cover {attack.target_cover_level}/4, 6E2 "
                        f"p45): no damage"
                    )
                location = (effect_for(location_for_roll(rolled), template=template)
                            if rolled else None)
        # 6E2 p.52's doubling for a target Surprised OUT of combat:
        # "Double the STUN damage before applying defenses (and, in
        # campaigns using the Hit Locations rules, before applying the
        # STUN modifier for a location)." It is passed INTO each damage
        # function rather than applied to a result here, because the two
        # damage types put the subtraction in different places and only
        # they know where "before defenses" is.
        surprise = getattr(attack, "surprise", None)
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

        # PENETRATING: a floor on BODY, whatever the defenses stopped.
        # 6E1 p.188's worked example -- "he takes 4 BODY - the minimum BODY
        # damage the Penetrating attack can cause with that roll" for a 4d6
        # attack -- so one BODY per die, replacing a smaller result and
        # never adding to a larger one. Impenetrable answers it level for
        # level (6E1 p.149). Both were parsed off the sheet and read by
        # nothing until this line.
        #
        # BEFORE the AVAD clause below deliberately: an AVAD that does no
        # BODY does no BODY, and a minimum of something is still a minimum
        # of BODY.
        from kirby_combat.resolution.penetrating import penetrating_floor

        floor = penetrating_floor(effective_power, target)
        if floor > body_dealt and not blocked_by_cover:
            audit_trail.append(
                f"Penetrating: BODY {body_dealt} raised to the minimum "
                f"{floor} ({floor} dice, 6E1 p188)"
            )
            body_dealt = floor

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

        audit_trail.append(
            f"Damage applied: STUN dealt={stun_dealt}, BODY dealt={body_dealt}"
        )

        # Use effective_power for downstream knockback / status checks
        # so they see the post-DN attack shape.
        power = effective_power

        # ------------------------------------------------------------------
        # 5. Knockback
        # ------------------------------------------------------------------
        knockback: KnockbackResult | None = None
        if template.use_knockback and body_dealt > 0:
            # Per 6E2 p116, the attacker rolls 2d6 (+ modifier dice) to
            # subtract from BODY rolled. We pass attack.dice.knockback as the
            # caller-rolled pool (caller is responsible for adding/removing
            # dice per the modifiers table).
            knockback = compute_knockback(
                body=body_dealt,
                knockback_dice=list(attack.dice.knockback),
                kb_resistance_m=defense.knockback_resistance,
                knockback_multiplier=template.knockback_multiplier,
                template=template,
            )
            audit_trail.extend(knockback.audit)

        # ------------------------------------------------------------------
        # 6. Status changes
        # ------------------------------------------------------------------
        stun_after = target.current_stun - stun_dealt
        body_after = target.current_body - body_dealt

        status_changes = determine_status_changes(
            stun_before=target.current_stun,
            stun_after=stun_after,
            body_before=target.current_body,
            body_after=body_after,
            con=target.con,
            max_body=target.max_body,
        )
        if status_changes:
            audit_trail.append(f"Status changes: {', '.join(status_changes)}")

        # ------------------------------------------------------------------
        # 7. END cost (simplified Phase 1)
        # ------------------------------------------------------------------
        # 1 END per 10 Active Points (6E1 p.132). This read the DICE
        # count, which is roughly double -- an 8d6 Blast is 40 Active
        # Points and costs 4 END, not 8 -- and a power on Charges or with
        # Reduced Endurance (0 END) was charged as if it were neither.
        end_spent = end_cost(effective_power)

        # ------------------------------------------------------------------
        # 8. Return
        # ------------------------------------------------------------------
        return AttackResult(
            hit=True,
            to_hit=to_hit,
            damage=damage,
            defense=defense,
            stun_dealt=stun_dealt,
            body_dealt=body_dealt,
            end_spent=end_spent,
            knockback=knockback,
            status_changes=status_changes,
            power_xmlid=power.xmlid,
            audit_trail=audit_trail,
        )
