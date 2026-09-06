"""Use a Presence Attack to demoralize an opponent.

HERO 6E Presence Attack (6E2 p129): roll the actor's PRE total in
d6 of effect against the target. If the result exceeds target's PRE
(by various tiers: equal = pause, +5 = target is impressed, +10 =
target hesitates, +20 = target is awed/cowed, +30 = target is
frozen). Fueled by character traits: appropriate alignment, dramatic
moment, intimidating SFX add dice.

Tactic: actor has substantial PRE (60+) and target has ordinary PRE
or a CODE OF HONOR / OVERCONFIDENT psych-lim. Spend a phase on PRE
attack — target's effective OCV/DCV drops next round.

Preconditions:
  * Actor PRE ≥ target.PRE + 10  AND
  * Target doesn't have INSANITY-level psych-lim (immune)
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register


@register
class PresenceAttackDemoralize(Tactic):
    name = "presence_attack_demoralize"
    basis = Basis(mechanism="6E2 p129", judgement="a PRE attack costs no END and can end a fight without a hit")
    priority = 25
    narrative_summary = (
        "Spend a phase on a Presence Attack to demoralize an opponent. "
        "Target's effective OCV/DCV drops by 1-3 next round depending "
        "on PRE differential. Best when actor has overwhelmingly higher "
        "PRE than target."
    )

    def applicable(self, situation: Situation) -> bool:
        actor_pre = (situation.actor.combat_stats().pre
                     if hasattr(situation.actor, "combat_stats") else 10)
        for enemy in situation.enemies:
            enemy_pre = (enemy.combat_stats().pre
                         if hasattr(enemy, "combat_stats") else 10)
            if actor_pre >= enemy_pre + 10:
                return True
        return False

    def execute(self, situation: Situation) -> Plan:
        actor_pre = situation.actor.combat_stats().pre
        # Pick the target with the largest PRE differential (= biggest
        # demoralization effect)
        best_target = None
        best_diff = 0
        for enemy in situation.enemies:
            enemy_pre = enemy.combat_stats().pre
            diff = actor_pre - enemy_pre
            if diff > best_diff:
                best_diff = diff
                best_target = enemy
        assert best_target is not None

        # PRE attack dice = actor's PRE / 5
        pre_dice = actor_pre // 5
        steps = [
            PlanStep(
                kind="presence_attack",
                target_id=best_target.id,
                notes=(
                    f"Roll {pre_dice}d6 PRE attack vs {best_target.id} "
                    f"(target PRE {best_target.combat_stats().pre}). "
                    f"PRE diff = +{best_diff}; tier breakdown: "
                    f"+5 impressed, +10 hesitates, +20 cowed, +30 frozen."
                ),
                params={"pre_dice": pre_dice,
                        "target_pre": best_target.combat_stats().pre},
            ),
        ]
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Actor PRE {actor_pre} vs target PRE "
                f"{best_target.combat_stats().pre} (Δ +{best_diff}). "
                f"Single-phase investment for a multi-phase effect "
                f"on target's combat values. Worst case: target shrugs "
                f"it off (1 phase lost). Best case: target frozen for "
                f"1+ phase, your team gets free hits."
            ),
            steps=steps,
            expected_outcome=(
                f"Probabilistic: average {pre_dice * 3.5:.0f} PRE-effect "
                f"vs {best_target.combat_stats().pre} target. "
                f"~50% chance of meaningful (≥+10) demoralization."
            ),
        )
