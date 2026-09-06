"""Abort to Block — use melee capability to intercept an incoming big hit.

Block is an HTH-based abort reaction: the defender rolls OCV against
the attacker's OCV; if they win, the attack is stopped entirely. It
requires an HTH attack (the blocking weapon) and costs the aborter
their next phase. Best used against a high-damage incoming strike
where eating the full damage would stun or KO the defender.

Preconditions:
  * Actor has at least one melee attack (range_m == 0) — Block is an
    HTH maneuver and requires the actor to have melee capability.

Terrain linkage:
  Pure reactive tactic. The chooser should select Block from the abort
  menu when a high-damage melee incoming is declared. The narrative
  text advises checking the action menu for the abort:block option.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.catalog._filters import _best_attack, _is_melee
from kirby_combat.tactics.library import register


def _has_melee_attack(situation: Situation) -> bool:
    """True if the actor has at least one melee (HTH) attack."""
    best = _best_attack(situation)
    if best is None:
        return False
    return _is_melee(best)


@register
class AbortToBlock(Tactic):
    name = "abort_to_block"
    basis = Basis(mechanism="6E2 p57", judgement="a stopped hit beats a spent phase when the incoming would stun")
    priority = 48
    narrative_summary = (
        "When a dangerous melee or ranged attack is incoming, abort to Block. "
        "Block is an OCV contest — if you win, the hit is stopped entirely. "
        "It costs your next phase but that's better than being stunned. "
        "Use it when the incoming attack would deal enough STUN to knock "
        "you out or force you into a critical health state. "
        "Check the action menu for the abort:block option when an enemy "
        "declares a big hit."
    )

    def applicable(self, situation: Situation) -> bool:
        return _has_melee_attack(situation)

    def execute(self, situation: Situation) -> Plan:
        best = _best_attack(situation)
        return Plan(
            tactic_name=self.name,
            rationale=(
                "Actor has HTH attack capability — eligible to abort to Block. "
                f"Using {best.name} ({best.damage_dice}d6) as the blocking weapon. "
                "Block stops the incoming attack entirely on an OCV win."
            ),
            steps=[
                PlanStep(
                    kind="wait",
                    power_xmlid=best.xmlid if best else None,
                    notes=(
                        "Hold and watch. When an enemy declares a high-damage "
                        "attack, abort to Block. Select abort:block from the "
                        "reaction menu. OCV vs OCV — if you win, the attack "
                        "is negated. Costs next phase but saves you from "
                        "a potentially stunning or killing blow."
                    ),
                    params={
                        "abort_to": "block",
                        "trigger": "big_incoming_attack",
                        "blocking_xmlid": best.xmlid if best else None,
                    },
                ),
            ],
            expected_outcome=(
                "Incoming attack negated on successful Block. "
                "Trade: next phase for avoiding a devastating hit."
            ),
        )
