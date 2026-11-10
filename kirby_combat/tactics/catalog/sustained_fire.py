"""Sustained fire — keep shooting one target through cover.

In a firefight behind cover, every blocked shot chips away at the
barrier protecting the enemy.  Repeated fire on one target erodes their
cover faster than switching targets.  The chip-damage mechanic means
each blocked shot DOES apply damage to the wall — eventually the wall
falls, leaving the enemy exposed mid-firefight.

Preconditions:
  * Actor has at least one ranged non-mental damaging attack, AND
  * an enemy is behind cover from where he stands. The whole premise is the
    wall; 0.32 offered it against men in the open, where "every blocked shot
    chips the wall" is false, and Plague fired at a dodging agent in the
    open nine times on its word (2026-11-10).

Terrain linkage:
  This tactic is most effective when terrain lines show the target is
  behind a low-DEF barrier. The chooser should maintain fire on the SAME
  target each phase rather than spreading shots, letting blocked rounds
  accumulate chip damage on the cover.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.catalog._filters import _best_ranged_attack, _enemies_in_cover
from kirby_combat.tactics.library import register


@register
class SustainedFire(Tactic):
    name = "sustained_fire"
    basis = Basis(mechanism="6E2 p89", judgement="area denial is worth more than a low-odds single shot")
    priority = 36
    narrative_summary = (
        "Pick one target and keep firing. Every shot that hits their cover "
        "chips the wall's BODY — even a blocked shot damages the barrier. "
        "Switching targets resets the chip progress. "
        "Sustained fire on one cover-user erodes their protection faster "
        "than spreading fire. "
        "Once their wall is gone, you get clean hits on a now-exposed target."
    )

    def applicable(self, situation: Situation) -> bool:
        return (_best_ranged_attack(situation) is not None
                and bool(_enemies_in_cover(situation)))

    def execute(self, situation: Situation) -> Plan:
        best = _best_ranged_attack(situation)
        # The nearest man behind cover: the one this tactic is about.
        target, _level = _enemies_in_cover(situation)[0]
        target_id = target.id
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Actor has ranged attack ({best.name}, {best.damage_dice}d6). "
                "Repeated fire on the same cover-user chips the barrier while "
                "applying END pressure each phase."
            ),
            steps=[
                PlanStep(
                    kind="attack",
                    target_id=target_id,
                    power_xmlid=best.xmlid,
                    notes=(
                        "Fire at the same target every phase. "
                        "Do NOT switch targets — chip damage accumulates on "
                        "their cover and eventually destroys it. "
                        "If the target is behind cover, the blocked shot "
                        "still damages the wall."
                    ),
                    params={"maintain_target": True, "chip_cover": True},
                ),
            ],
            expected_outcome=(
                "Target's cover eroded over 2-3 phases, then exposed to "
                "clean hits. END pressure forces the target to keep defending."
            ),
        )
