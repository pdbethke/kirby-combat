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
  * Actor health is ``"healthy"`` --- the rung
    `kirby_combat.health.classify_health` owns (STUN at or above 50% of
    max AND BODY above 0). A hurt high-PD character should still take
    cover (see ``take_cover_when_hurt``), which asks the same function,
    so the two tactics cannot end up on different sides of one line.

Terrain linkage:
  Primarily a meta-decision tactic. The narrative text advises the chooser
  not to choose abort actions when the actor has high PD and full health.
"""
from __future__ import annotations

from kirby_combat.health import classify_health
from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register

# Total physical defense (pd + rpd) threshold. combat_stats().pd is
# base PD + bare PD powers only — FORCEFIELD/RESISTANTPROTECTION land
# in .rpd, so the gate sums both. Calibrated against the corpus pair
# (2026-06-11): brick-Gorgon has pd=15/rpd=0 and MUST pass (he's the
# seeded brick archetype); Cheshire has pd=14/rpd=0 and should not.
# A 20 threshold (even on pd+rpd) excludes the corpus brick entirely.
_MIN_PD_TO_STAND = 15


def _is_high_pd_and_healthy(situation: Situation) -> bool:
    """High enough defenses to trade, and whole enough to want to.

    THE HEALTH HALF IS NOT THIS MODULE'S TO DECIDE. It kept its own
    `_STUN_HEALTHY_PCT = 50` and its own `current_body <= 0` test --- a
    fifth copy of the ladder `kirby_combat.health.classify_health` owns,
    and the same one: "healthy" there is exactly STUN at or above half
    AND BODY above zero. Two statements of one judgement is two
    judgements the day either moves a rung, and this tactic and
    `take_cover_when_hurt` are meant to be opposite sides of the SAME
    line.

    THE ONE THING THAT IS THIS MODULE'S: a combatant with no STUN
    maximum. `classify_health` answers "healthy" for him, because there
    is no ladder to place him on. That is the right answer to "how hurt
    is he" and the wrong answer to "should he stand and trade" --- a
    posture about absorbing STUN needs a STUN track to absorb it with ---
    so the refusal is stated here, where the question is asked, rather
    than pushed into the ladder where it would change what "healthy"
    means for everybody.
    """
    actor = situation.actor
    stats = actor.combat_stats()
    if (stats.pd + stats.rpd) < _MIN_PD_TO_STAND:
        return False
    if actor.max_stun <= 0:
        return False
    return classify_health(actor) == "healthy"


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
