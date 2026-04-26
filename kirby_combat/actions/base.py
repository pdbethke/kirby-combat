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
        # 2. Damage
        # ------------------------------------------------------------------
        damage = compute_damage(power, attack.dice, template, hit_location=attack.aim)
        audit_trail.extend(damage.audit)

        # ------------------------------------------------------------------
        # 3. Defense
        # ------------------------------------------------------------------
        defense = compute_defense(target, power)
        audit_trail.extend(defense.audit)

        # ------------------------------------------------------------------
        # 4. Apply damage
        # ------------------------------------------------------------------
        if power.damage_type == "killing":
            # Killing: total defense stops STUN, resistant defense stops BODY
            stun_dealt = max(0, damage.stun - defense.total_defense)
            body_dealt = max(0, damage.body - defense.resistant_defense)
        else:
            # Normal: total defense stops both STUN and BODY
            stun_dealt = max(0, damage.stun - defense.total_defense)
            body_dealt = max(0, damage.body - defense.total_defense)

        audit_trail.append(
            f"Damage applied: STUN dealt={stun_dealt}, BODY dealt={body_dealt}"
        )

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
