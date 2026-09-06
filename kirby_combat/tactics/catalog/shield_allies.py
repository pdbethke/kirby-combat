"""Shield allies — use high PD to interpose and protect team members.

A combatant with exceptional defenses (pd + rpd ≥ 15) can act as a
shield for lower-defense allies. This means deliberately positioning
to draw fire, absorbing hits that would devastate a teammate, or
physically interposing between an attacker and a vulnerable ally.

Preconditions:
  * Actor has at least one living ally.
  * Actor's total physical defense (combat_stats().pd + .rpd —
    rpd carries FORCEFIELD/RESISTANTPROTECTION) is ≥ threshold (15,
    corpus-brick calibrated). This ensures the actor can actually
    survive the hits they're drawing away from allies.

Terrain linkage:
  Most effective when terrain puts allies in exposed positions.
  The chooser should position the actor between the main threat and
  the most vulnerable ally.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register

# Total physical defense (pd + rpd) threshold for viable shielding.
# combat_stats().pd is base PD + bare PD powers only — FORCEFIELD /
# RESISTANTPROTECTION land in .rpd, so the gate sums both. Calibrated
# against the corpus pair (2026-06-11): brick-Gorgon has pd=15/rpd=0
# and MUST pass (he's the seeded brick archetype); Cheshire has
# pd=14/rpd=0 and should not. A 20 threshold (even on pd+rpd)
# excludes the corpus brick entirely.
_MIN_PD_TO_SHIELD = 15


@register
class ShieldAllies(Tactic):
    name = "shield_allies"
    basis = Basis(judgement="a downed ally is a permanent loss of damage output; a spent phase is not")
    priority = 46
    narrative_summary = (
        "Your heavy defenses make you the right person to take the hits. "
        "Position yourself between the main threat and your most vulnerable "
        "ally — draw fire toward you and away from them. "
        "Your PD can absorb what would devastate a teammate. "
        "Interpose physically: get adjacent to the threatened ally and "
        "let enemies waste attacks on you instead of on them."
    )

    def applicable(self, situation: Situation) -> bool:
        if not situation.allies:
            return False
        stats = situation.actor.combat_stats()
        return (stats.pd + stats.rpd) >= _MIN_PD_TO_SHIELD

    def execute(self, situation: Situation) -> Plan:
        stats = situation.actor.combat_stats()
        pd = stats.pd + stats.rpd
        # Target the most dangerous enemy (highest-damage attacker)
        target = situation.enemies[0] if situation.enemies else None
        target_id = target.id if target else None
        # Find the most vulnerable ally (lowest max_stun)
        most_vulnerable_ally = (
            min(situation.allies, key=lambda a: a.combat_stats().max_stun)
            if situation.allies else None
        )
        ally_id = most_vulnerable_ally.id if most_vulnerable_ally else None
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Actor has PD {pd} (≥{_MIN_PD_TO_SHIELD} threshold). "
                "High defenses make this actor a viable shield for lower-PD "
                f"allies. Most vulnerable ally: {ally_id}."
            ),
            steps=[
                PlanStep(
                    kind="move",
                    target_id=ally_id,
                    notes=(
                        "Move to interpose between the main attacker and the "
                        "most vulnerable ally. Position adjacent to the ally "
                        "to physically block line-of-attack."
                    ),
                    params={"interpose_for_ally": ally_id, "absorb_fire": True},
                ),
                PlanStep(
                    kind="attack",
                    target_id=target_id,
                    notes=(
                        "Strike the main threat to make them choose between "
                        "attacking you (high PD) or the protected ally "
                        "(requires closing past you)."
                    ),
                ),
            ],
            expected_outcome=(
                "Most vulnerable ally is shielded this phase. "
                "Attacker forced to target the high-PD actor or disengage."
            ),
        )
