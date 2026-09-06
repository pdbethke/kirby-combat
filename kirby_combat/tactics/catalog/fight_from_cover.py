"""Fight from behind cover — move:cover then shoot.

A ranged combatant has nothing to gain from standing in the open.
Move to the nearest cover or partial-cover position, then fire.
Blocked shots chip the wall but cost END — acceptable exchange when
staying alive longer wins the attrition fight.

Preconditions:
  * Actor has at least one ranged damaging attack (range_m > 0,
    damage_dice > 0, non-mental).

Terrain linkage:
  The ``move:cover`` action in the enumerated menu expresses this
  advice concretely. This tactic's narrative text signals the chooser to
  combine a move to cover with a ranged attack in the same phase.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.catalog._filters import _best_ranged_attack
from kirby_combat.tactics.library import register


def _has_ranged_attack(situation: Situation) -> bool:
    return _best_ranged_attack(situation) is not None


@register
class FightFromCover(Tactic):
    name = "fight_from_cover"
    basis = Basis(judgement="cover is free DCV; giving it up needs a reason")
    priority = 40
    narrative_summary = (
        "Use cover and fire from safety. Move behind a wall, crate, or "
        "barrier first — choose the move_to_cover action — then shoot at range. "
        "If a shot is blocked by an obstacle it chips the cover and still "
        "costs the target END when they dodge. Never stand in the open "
        "when you have reach and the enemy has to close."
    )

    def applicable(self, situation: Situation) -> bool:
        return _has_ranged_attack(situation)

    def execute(self, situation: Situation) -> Plan:
        best = _best_ranged_attack(situation)
        target = (situation.enemies[0] if situation.enemies else None)
        target_id = target.id if target else None
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Actor has ranged attack ({best.name}, {best.damage_dice}d6, "
                f"range {best.range_m}m). Moving to cover then shooting "
                "maximises defense while maintaining offense."
            ),
            steps=[
                PlanStep(
                    kind="move",
                    notes=(
                        "Move to nearest cover position — choose move:cover "
                        "from the action menu if available. Half-move to keep "
                        "the attack action this phase."
                    ),
                    params={"prefer_cover": True},
                ),
                PlanStep(
                    kind="attack",
                    target_id=target_id,
                    power_xmlid=best.xmlid,
                    notes=(
                        "Fire at range from behind cover. "
                        "Blocked shots chip the barrier but still apply END pressure."
                    ),
                ),
            ],
            expected_outcome=(
                "Actor gains cover defense while landing a ranged attack. "
                "Net advantage: reduced incoming damage next phase."
            ),
        )
