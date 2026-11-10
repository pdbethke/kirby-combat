"""Use a Presence Attack to demoralize an opponent.

HERO 6E Presence Attack (6E2 p.138-139): roll PRE/5 d6 against the
target's PRE. At least his PRE: impressed (he hesitates). PRE +10: very
impressed (only a Half Phase next Phase). PRE +20: awed (he does not act for
a Full Phase, ½ DCV). PRE +30: cowed (0 DCV; he may surrender or run).
Each repeat at the same man is 1d6 less (6E2 p.140).

0.32 told the reader "OCV/DCV drops by 1-3", which is no tier of the book's,
and stayed on the page after his Presence Attacks had done nothing. Plague
made three group Presence Attacks at the same agents; the last two did
nothing at all (2026-11-10).

Preconditions:
  * Actor PRE >= some enemy's PRE + 10, AND
  * his last two Presence Attacks this fight were not both met with no
    effect on anyone: that is evidence, and the next is 1d6 weaker.
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
        "A Presence Attack rolls PRE/5 d6 against his PRE (6E2 p138): at "
        "least his PRE he hesitates; +10 he gets only a Half Phase next "
        "Phase; +20 he loses a Full Phase and is at half DCV; +30 he is at "
        "0 DCV and may run or surrender. Each repeat at the same man is 1d6 "
        "less. Worth it when your dice clearly beat their PRE."
    )

    @staticmethod
    def _shouted_in_vain(situation: Situation) -> bool:
        """His last two Presence Attacks this fight both did nothing to
        anyone (`own_record.own_actions`)."""
        session = getattr(situation, "session", None)
        if session is None:
            return False
        from kirby_combat.own_record import own_actions

        shouts = [p for p in own_actions(session, str(situation.actor.id))
                  if p.get("kind") in ("presence_attack", "presence_attack_group")]
        if len(shouts) < 2:
            return False

        def nothing(p: dict) -> bool:
            effects = p.get("effects") or {}
            tiers = set(effects.values()) if effects else {p.get("effect") or p.get("tier")}
            return tiers <= {"no_effect", None}

        return all(nothing(p) for p in shouts[-2:])

    def applicable(self, situation: Situation) -> bool:
        if self._shouted_in_vain(situation):
            return False
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
                    f"PRE diff = +{best_diff}; tiers (6E2 p138): his PRE "
                    f"impressed, +10 very impressed, +20 awed, +30 cowed."
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
