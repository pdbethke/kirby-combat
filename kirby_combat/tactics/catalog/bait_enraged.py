"""Bait an Enraged enemy into hitting their teammate.

HERO 6E ENRAGED disadvantage (6E1 p426): when the trigger condition
fires, the character must roll their EGO to retain control. On
failure they enter a Berserk-like state — attacking the nearest
target (which may be an ally if positioned well).

Tactic: actor with a strong PRE attack or Persuasion taunts the
enraged enemy, triggers Enrage, then positions so the enemy's
straight-line lash-out catches their teammate.

Preconditions:
  * One enemy has ENRAGED complication
  * Actor has PRE ≥ enemy.PRE + 5  OR  PERSUASION 13- skill
  * That enemy has at least one ally adjacent or nearby (catchable
    in line-of-attack)

Plan: 2 phases.
  Phase A: PRE attack (taunt)  — triggers ENRAGED check
  Phase B: Move so target's nearest opponent is the ally
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.complications import find_complication
from kirby_combat.tactics.library import register


@register
class BaitEnraged(Tactic):
    name = "bait_enraged"
    basis = Basis(mechanism="6E1 p426", judgement="an enraged enemy loses its CV bonuses and its judgement")
    priority = 50
    narrative_summary = (
        "Taunt an enemy with the ENRAGED disadvantage into attacking "
        "their teammate instead of you. Requires either superior PRE "
        "or a taunt-class skill (Persuasion / Conversation / Acting)."
    )

    def applicable(self, situation: Situation) -> bool:
        actor_pre = (situation.actor.combat_stats().pre
                     if hasattr(situation.actor, "combat_stats") else 10)
        has_taunt_skill = any(
            sk in situation.actor_skills for sk in
            ("PERSUASION", "CONVERSATION", "ACTING", "ORATORY")
        )
        for enemy in situation.enemies:
            comps = situation.enemy_complications.get(enemy.id, [])
            if not find_complication(comps, xmlid="ENRAGED"):
                continue
            enemy_pre = (enemy.combat_stats().pre
                         if hasattr(enemy, "combat_stats") else 10)
            if not (actor_pre >= enemy_pre + 5 or has_taunt_skill):
                continue
            # Need at least one OTHER enemy/ally the enraged target
            # might reach. We use the SCENE's other living enemies as
            # potential redirect-targets.
            other_targets = [e for e in situation.enemies if e.id != enemy.id]
            other_targets += situation.allies
            if not other_targets:
                continue
            return True
        return False

    def execute(self, situation: Situation) -> Plan:
        # Pick the enraged enemy (first applicable)
        target = None
        comp = None
        for enemy in situation.enemies:
            comps = situation.enemy_complications.get(enemy.id, [])
            comp = find_complication(comps, xmlid="ENRAGED")
            if comp:
                target = enemy
                break
        assert target is not None and comp is not None

        redirect = None
        candidates = [e for e in situation.enemies if e.id != target.id] + situation.allies
        if candidates:
            redirect = candidates[0]

        steps = [
            PlanStep(
                kind="presence_attack",
                target_id=target.id,
                notes=(
                    f"Taunt {target.id} to trigger ENRAGED. Mock his "
                    f"strongest PSYCH-LIM tied to rage."
                ),
                params={"comp_keywords": list(comp.trigger_keywords)},
            ),
            PlanStep(
                kind="move",
                notes=(
                    f"Reposition so the line from {target.id} to nearest "
                    f"target passes through {redirect.id if redirect else 'an ally'} — "
                    f"his enraged lash-out catches them, not me."
                ),
                params={"redirect_through": redirect.id if redirect else None},
            ),
        ]
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"{target.id} carries ENRAGED ({comp.alias or comp.name}). "
                f"PRE attack triggers the rage check; positioning "
                f"redirects his attack onto a teammate. Two phases: "
                f"taunt → reposition. Engine handles the EGO roll for "
                f"rage suppression and the redirected to-hit on whoever "
                f"ends up in his arc."
            ),
            steps=steps,
            expected_outcome=(
                f"Best case: {target.id} fails his EGO roll, attacks "
                f"{redirect.id if redirect else 'closest target'} (his ally), "
                f"wasting a phase and damaging team cohesion. "
                f"Worst case: {target.id} resists; we lose 2 phases."
            ),
        )
