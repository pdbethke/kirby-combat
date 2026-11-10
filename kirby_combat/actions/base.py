"""Base attack action with the shared resolution pipeline."""
from __future__ import annotations

from kirby_combat.models import AttackInput, AttackResult, KnockbackResult
from kirby_combat.endurance import end_cost
from kirby_combat.resolution.hit_location import (
    effect_for, exposed_through_cover, location_for_roll,
    uses_hit_locations,
)
from kirby_combat.resolution.knockback import (
    compute_knockback, does_knockback, knockback_body,
)
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
        # An Area's victims and a lingering power's later damage were hit
        # by a roll made somewhere else (see `AttackInput.fixed_to_hit`).
        fixed = getattr(attack, "fixed_to_hit", None)
        to_hit = fixed if fixed is not None else resolve_to_hit(attack, template)
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
        from kirby_combat.resolution.damage_taken import damage_taken

        taken = damage_taken(
            power, target, attack.dice, template, aim=attack.aim,
            location=location, blocked_by_cover=blocked_by_cover,
            surprise=getattr(attack, "surprise", None),
            dc_modifier=attack.dc_modifier,
            damage_taken_factor=getattr(attack, "damage_taken_factor", 1.0),
        )
        audit_trail.extend(taken.audit)
        stun_dealt, body_dealt = taken.stun, taken.body
        damage, defense = taken.damage, taken.defense
        effective_power = taken.power

        # Use effective_power for downstream knockback / status checks
        # so they see the post-DN attack shape.
        power = effective_power

        # ------------------------------------------------------------------
        # 5. Knockback
        # ------------------------------------------------------------------
        knockback: KnockbackResult | None = None
        # 6E2 p.116: "Use the total amount of BODY ROLLED on the attack
        # dice, regardless of the target's defenses". This used BODY DEALT
        # -- after defenses -- so a punch that a brick's PD stopped cold
        # never moved him, and one that got through moved him by what got
        # through. And it ran on an EMPTY knockback pool, because nothing
        # rolled one: BODY minus a 0 roll, every hit, twice as far as the
        # book. The pool is now rolled at the session door
        # (`impact.knockback_dice_for`) and an attack resolved without one
        # does no Knockback rather than the maximum.
        knockback_owed = bool(
            template.use_knockback and damage.body > 0
            and does_knockback(power)
            # The shot that found the cover (6E2 p.45) never touched him.
            and not blocked_by_cover)
        if knockback_owed and attack.dice.knockback:
            # Per 6E2 p116, the attacker rolls 2d6 (+ modifier dice) to
            # subtract from BODY rolled. We pass attack.dice.knockback as the
            # caller-rolled pool (caller is responsible for adding/removing
            # dice per the modifiers table).
            knockback = compute_knockback(
                body=knockback_body(power, damage.body, attack.knockback_body_bonus),
                knockback_dice=list(attack.dice.knockback),
                kb_resistance_m=defense.knockback_resistance,
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
            knockback_owed=knockback_owed and knockback is None,
        )
