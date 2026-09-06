"""Stand and take it — brick-style low-abort posture.

A combatant with exceptional physical defenses who is at healthy STUN
levels should NOT abort. Aborting costs the next phase and lets the
enemy dictate tempo. A brick who can absorb 15-20 STUN per hit without
breaking health states gains more from a steady attack rhythm than from
burning phases on reactive defense.

Preconditions:
  * Actor total physical defense (combat_stats().pd + .rpd — rpd
    carries FORCEFIELD/RESISTANTPROTECTION) ≥ threshold (15) — high
    enough to make absorbing hits viable.
  * Actor health is at "default" (STUN ≥ 50% of max AND BODY > 0).
    A hurt high-PD character should still take cover (see
    ``take_cover_when_hurt``). This tactic applies only when healthy.

Terrain linkage:
  Primarily a meta-decision tactic. The narrative text advises the chooser
  not to choose abort actions when the actor has high PD and full health.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register

# Total physical defense (pd + rpd) threshold. combat_stats().pd is
# base PD + bare PD powers only — FORCEFIELD/RESISTANTPROTECTION land
# in .rpd, so the gate sums both. Calibrated against the corpus pair
# (2026-06-11): brick-Gorgon has pd=15/rpd=0 and MUST pass (he's the
# seeded brick archetype); Cheshire has pd=14/rpd=0 and should not.
# A 20 threshold (even on pd+rpd) excludes the corpus brick entirely.
_MIN_PD_TO_STAND = 15
_STUN_HEALTHY_PCT = 50  # must be at or above this to stand


def _is_high_pd_and_healthy(situation: Situation) -> bool:
    actor = situation.actor
    stats = actor.combat_stats()
    if (stats.pd + stats.rpd) < _MIN_PD_TO_STAND:
        return False
    max_stun = actor.max_stun
    if max_stun <= 0:
        return False
    stun_pct = round(100 * actor.current_stun / max_stun)
    # Must be at "default" health: STUN ≥ 50% AND BODY > 0
    if stun_pct < _STUN_HEALTHY_PCT:
        return False
    if actor.current_body <= 0:
        return False
    return True


@register
class StandAndTakeIt(Tactic):
    name = "stand_and_take_it"
    basis = Basis(judgement="trading hits favours whoever has more STUN left")
    priority = 43
    narrative_summary = (
        "You are a wall — stand your ground and don't abort. "
        "Your defenses are high enough to absorb what they throw at you. "
        "Every phase you spend aborting is a phase you're NOT hitting back. "
        "Absorb the hit, apply your defenses, and attack on your phase. "
        "The math favors you: high PD means their damage is reduced, "
        "and your steady attack output will end the fight faster "
        "than a defensive abort loop."
    )

    def applicable(self, situation: Situation) -> bool:
        return _is_high_pd_and_healthy(situation)

    def execute(self, situation: Situation) -> Plan:
        stats = situation.actor.combat_stats()
        pd = stats.pd + stats.rpd
        stun_pct = round(
            100 * situation.actor.current_stun
            / max(situation.actor.max_stun, 1)
        )
        target = situation.enemies[0] if situation.enemies else None
        target_id = target.id if target else None
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Actor at {stun_pct}% STUN with PD {pd} — "
                "high defenses + healthy means absorbing hits is the "
                "better play vs aborting. Keeps attack tempo."
            ),
            steps=[
                PlanStep(
                    kind="attack",
                    target_id=target_id,
                    notes=(
                        "Attack on your phase. Do NOT abort when an incoming "
                        "attack is declared — absorb it and keep your tempo. "
                        "Your PD reduces their damage; your attacks will "
                        "end the fight faster than trading aborts."
                    ),
                    params={"do_not_abort": True, "maintain_offense": True},
                ),
            ],
            expected_outcome=(
                "Actor maintains attack tempo, absorbs incoming damage via "
                f"PD {pd}, and ends the fight faster than defensive play."
            ),
        )
