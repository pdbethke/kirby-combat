"""Grab and Throw — seize the enemy and hurl them into hazards or walls.

A melee-dominant combatant with high STR can use enemies as projectiles.
Grab on one phase; throw on the next.  Aim the throw toward a hazard
(acid pool, fire zone, edge) or a hard wall for bonus impact damage.
Even without environmental targets a throw creates distance and
disrupts the enemy's next action.

Preconditions:
  * Actor's best attack is melee (range_m == 0) AND STR ≥ 30
    (≥6d6 STR unarmed — robust enough to reliably complete a grab).

Terrain linkage:
  Most effective when terrain lines show a hazard within throw range
  (~8m from current position).  The narrative text signals the chooser to
  combine a Grab action with a directed Throw toward the nearest
  hazard or wall.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.catalog._filters import _best_attack, _is_melee
from kirby_combat.tactics.library import register

_MIN_STR_FOR_RELIABLE_GRAB = 30  # ≥6d6 STR — competitive grab attempt


def _actor_str(situation: Situation) -> int:
    return situation.actor.combat_stats().str_


@register
class GrabAndThrow(Tactic):
    name = "grab_and_throw"
    basis = Basis(mechanism="6E2 p62", judgement="a grabbed enemy stops shooting; throwing adds velocity damage")
    priority = 44
    narrative_summary = (
        "Grab an enemy and throw them — into a hazard, into a wall, "
        "or just across the room to buy distance. "
        "Phase 1: declare a Grab action — STR contest locks them down. "
        "Phase 2: throw them toward the nearest pool, fire zone, or "
        "hard surface for compound damage. "
        "Even a throw into open air resets their positioning and may "
        "keep them off you for a phase. "
        "If a hazard is nearby, aim the throw INTO it."
    )

    def applicable(self, situation: Situation) -> bool:
        best = _best_attack(situation)
        if best is None:
            return False
        if not _is_melee(best):
            return False
        return _actor_str(situation) >= _MIN_STR_FOR_RELIABLE_GRAB

    def execute(self, situation: Situation) -> Plan:
        best = _best_attack(situation)
        target = (situation.enemies[0] if situation.enemies else None)
        target_id = target.id if target else None
        str_val = _actor_str(situation)
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Actor has STR {str_val} and melee-dominant attack "
                f"({best.name}, {best.damage_dice}d6). Grab+throw into a "
                "hazard combines grip damage with environmental damage."
            ),
            steps=[
                PlanStep(
                    kind="attack",
                    target_id=target_id,
                    power_xmlid="GRAB",
                    notes=(
                        "Declare a Grab action against the target. "
                        "STR contest — if won, target is held."
                    ),
                    params={"action_kind": "grab"},
                ),
                PlanStep(
                    kind="attack",
                    target_id=target_id,
                    power_xmlid="THROW",
                    notes=(
                        "Throw toward nearest hazard (pool, fire, wall, ledge). "
                        "If no hazard is in range, throw to create distance "
                        "and disrupt their next action."
                    ),
                    params={"action_kind": "throw", "aim_for_hazard": True},
                ),
            ],
            expected_outcome=(
                "Target relocated into a hazard or stunned by impact. "
                "Environmental damage compounds each phase they remain in the hazard."
            ),
        )
