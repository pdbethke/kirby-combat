"""Take cover when hurt — move to safety when health is not at default.

A combatant who has taken significant damage should stop fighting from
the open. Moving to cover buys time for recovery and reduces incoming
damage next phase. The health thresholds mirror ``_classify_health``
in ``situation_builder``: wounded = STUN < 50%; critical = STUN ≤ 25%
or BODY ≤ 0.

Preconditions:
  * Actor's health is NOT at the "default" state — i.e. current STUN
    has dropped below 50% of max OR current BODY has reached 0 or
    below. (Mirrors ``situation_builder._classify_health`` logic;
    duplicated here to keep tactics DB-free and cycle-free.)

Terrain linkage:
  The ``move_to_cover`` action in the enumerated menu is the concrete
  expression of this advice. The chooser should choose it when the actor
  is in any non-default health state.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register

# Mirrors situation_builder._classify_health thresholds.
# "wounded": STUN < 50%; "critical": STUN ≤ 25% or BODY ≤ 0.
# Together: health ≠ default ⟺ stun_pct < 50 OR body_pct <= 0.
_STUN_WOUNDED_PCT = 50
_STUN_CRITICAL_PCT = 25


def _health_is_not_default(situation: Situation) -> bool:
    actor = situation.actor
    max_stun = actor.max_stun
    max_body = actor.max_body
    if max_stun <= 0:
        return False
    stun_pct = round(100 * actor.current_stun / max_stun)
    body_pct = round(100 * actor.current_body / max(max_body, 1))
    # critical: STUN ≤ 25% or BODY ≤ 0
    if body_pct <= 0 or stun_pct <= _STUN_CRITICAL_PCT:
        return True
    # wounded: STUN < 50%
    return stun_pct < _STUN_WOUNDED_PCT


@register
class TakeCoverWhenHurt(Tactic):
    name = "take_cover_when_hurt"
    basis = Basis(judgement="a character below half STUN loses more to one more hit than to one lost phase")
    priority = 55
    narrative_summary = (
        "You are injured — get behind cover NOW. "
        "Choose the move_to_cover action: half-move to the nearest "
        "wall, crate, or barrier before anything else this phase. "
        "Standing in the open while wounded is how fights end badly. "
        "Cover reduces incoming damage; once you are protected you can "
        "counter-attack from safety next phase."
    )

    def applicable(self, situation: Situation) -> bool:
        return _health_is_not_default(situation)

    def execute(self, situation: Situation) -> Plan:
        stun_pct = round(
            100 * situation.actor.current_stun
            / max(situation.actor.max_stun, 1)
        )
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Actor at {stun_pct}% STUN — health is NOT at default. "
                "Moving to cover is the priority defensive action to reduce "
                "further incoming damage."
            ),
            steps=[
                PlanStep(
                    # See fight_from_cover: kind="move" with the intent in
                    # the notes got an arbitrary move offer.
                    kind="move_to_cover",
                    notes=(
                        "Half-move to the nearest available cover position. "
                        "Use the remaining action for a quick shot from cover "
                        "if a target is in range."
                    ),
                    params={"prefer_cover": True, "priority": "defensive"},
                ),
            ],
            expected_outcome=(
                "Actor gains cover defense this phase, reducing incoming "
                "STUN/BODY damage next phase. Sets up counter-attack from safety."
            ),
        )
