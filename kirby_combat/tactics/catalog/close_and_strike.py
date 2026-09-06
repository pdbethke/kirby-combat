"""Close and Strike — get in fast, hit hard.

When a combatant's best attack is melee, the correct opening play is to
close the distance and hit.  Half-move to get adjacent, then swing with
the strongest HTH or HKA.  If already adjacent, skip the move and
strike immediately.

Preconditions:
  * Actor's best attack (highest damage_dice) is melee (range_m == 0
    or uses_str True with no range).

The STR-based strike through ``actor.attacks`` already reflects the
STR/5 damage dice contribution, so a 40 STR combatant shows 8d6 for
their unarmed strike and 12d6 for a levels=4 HANDTOHANDATTACK — that
is the comparison baseline.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.catalog._filters import _best_attack, _is_melee
from kirby_combat.tactics.library import register


@register
class CloseAndStrike(Tactic):
    name = "close_and_strike"
    basis = Basis(judgement="closing and striking in one phase denies the target a phase to retreat")
    priority = 38
    narrative_summary = (
        "Your strongest attack is melee range. Close the distance fast — "
        "half-move to get adjacent, then hit with everything. "
        "Don't waste a phase waiting for them to come to you. "
        "Once adjacent use your hardest hitting power each phase. "
        "If enemies are spread, target the most dangerous one first."
    )

    def applicable(self, situation: Situation) -> bool:
        best = _best_attack(situation)
        if best is None:
            return False
        return _is_melee(best)

    def execute(self, situation: Situation) -> Plan:
        best = _best_attack(situation)
        target = (situation.enemies[0] if situation.enemies else None)
        target_id = target.id if target else None
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Best attack is melee ({best.name}, {best.damage_dice}d6, "
                f"range_m={best.range_m}). Close immediately and strike."
            ),
            steps=[
                PlanStep(
                    kind="attack",
                    target_id=target_id,
                    power_xmlid=best.xmlid,
                    notes=(
                        "Half-move to get adjacent, then strike with best "
                        "melee attack. If already adjacent, skip the move "
                        "and go straight to the hit."
                    ),
                    params={"close_first": True},
                ),
            ],
            expected_outcome=(
                f"{best.damage_dice}d6 landing this phase. Enemy must absorb "
                "or abort — either outcome is advantageous."
            ),
        )
