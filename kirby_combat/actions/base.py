"""Base attack action with the shared resolution pipeline."""
from __future__ import annotations

from kirby_combat.models import AttackInput, AttackResult, DamageResult, DefenseProfile, KnockbackResult, ToHitResult
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
                end_spent=max(1, power.damage_dice),
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
        if effective_power.damage_type == "killing":
            stun_dealt = max(0, damage.stun - defense.total_defense)
            body_dealt = max(0, damage.body - defense.resistant_defense)
        else:
            stun_dealt = max(0, damage.stun - defense.total_defense)
            body_dealt = max(0, damage.body - defense.total_defense)

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
        end_spent = max(1, power.damage_dice)

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
