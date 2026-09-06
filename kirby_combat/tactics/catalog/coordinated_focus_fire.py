"""Coordinated focus fire on the enemy's softest target.

When an actor has 1+ allies and the enemies have a clear glass-cannon
(low STUN/BODY relative to peers), the right play is to coordinate
attacks all on the same target in a single segment so the target
falls before they can recover or abort.

Preconditions:
  * Actor has at least 1 living ally
  * Enemies span a wide STUN range (some have ≥1.5x the lowest)
  * Actor's primary attack has range that reaches the soft target

Plan: 1 phase but coordinated.
  All allies (this phase + actors-acting-soon) target the lowest-
  STUN enemy. Single phase but team scope.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register


@register
class CoordinatedFocusFire(Tactic):
    name = "coordinated_focus_fire"
    basis = Basis(judgement="concentrating fire kills one enemy sooner, which removes a whole attacker")
    priority = 30
    narrative_summary = (
        "Coordinate with allies to focus all attacks on the squishiest "
        "enemy this segment. Drops them before they can abort or "
        "recover. Best when there's a clear glass-cannon."
    )

    def applicable(self, situation: Situation) -> bool:
        if not situation.allies:
            return False
        living = [e for e in situation.enemies
                  if e.state.current_stun > 0]
        if len(living) < 2:
            return False
        stuns = [e.combat_stats().max_stun for e in living]
        if max(stuns) < min(stuns) * 1.5:
            return False  # no clear soft target
        return True

    def execute(self, situation: Situation) -> Plan:
        living = [e for e in situation.enemies
                  if e.state.current_stun > 0]
        target = min(living, key=lambda e: e.combat_stats().max_stun)
        ally_count = len(situation.allies)
        steps = [
            PlanStep(
                kind="attack",
                target_id=target.id,
                notes=(
                    f"All available allies fire on {target.id} this "
                    f"segment — {ally_count} ally(s) coordinate."
                ),
                params={"call_ally_focus_fire": True},
            ),
        ]
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"{target.id} has the lowest max_stun "
                f"({target.combat_stats().max_stun}) of {len(living)} "
                f"enemies — fragile relative to peers. Concentrating "
                f"{ally_count + 1} attacks in one segment likely drops "
                f"them before they can abort or recover."
            ),
            steps=steps,
            expected_outcome=(
                f"{target.id} stunned/KO'd this segment if 2+ attacks "
                f"land. Saves segments overall vs distributed fire."
            ),
        )
