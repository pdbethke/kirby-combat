"""Reposition when spotted — sniper defensive: move to new cover when hurt.

A ranged combatant who has taken damage in their current position has
been spotted. Their cover advantage is compromised and enemies are
now zeroing in. The correct play is to immediately reposition to a
new cover position before taking more fire — then continue shooting
from the new location.

Preconditions:
  * Actor health is not ``"healthy"`` (STUN < 50% of max OR BODY ≤ 0).
    The ladder belongs to `kirby_combat.health.classify_health`, which
    ``take_cover_when_hurt`` asks too — one reading of one number, not
    two modules agreeing by inspection.
  * Actor has at least one ranged non-mental attack. A melee-only
    combatant who has taken damage should use ``take_cover_when_hurt``
    instead (no need for a new shooting position).

Terrain linkage:
  The ``move_to_cover`` action in the enumerated menu is the primary
  expression. This tactic specifically emphasises choosing a DIFFERENT
  cover position from the current one, not just ducking behind the
  nearest wall.
"""
from __future__ import annotations

from kirby_combat.health import classify_health, stun_percent
from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.catalog._filters import _best_ranged_attack
from kirby_combat.tactics.library import register


@register
class RepositionWhenSpotted(Tactic):
    name = "reposition_when_spotted"
    basis = Basis(judgement="a known position is a targeted position")
    priority = 51
    narrative_summary = (
        "You've taken fire in your current position — you've been spotted. "
        "Move to a NEW cover location immediately: your current spot is "
        "zeroed in and staying there means eating more hits. "
        "Use move_to_cover to relocate — prioritise a position with a "
        "different angle on the fight so enemies lose their sight line. "
        "Once repositioned, resume firing from the new cover."
    )

    def applicable(self, situation: Situation) -> bool:
        if classify_health(situation.actor) == "healthy":
            return False
        return _best_ranged_attack(situation) is not None

    def execute(self, situation: Situation) -> Plan:
        best = _best_ranged_attack(situation)
        # The SAME percentage the ladder is cut from. Recomputed here
        # until 2026-09-17, so the number the reader was shown and the
        # number `classify_health` branched on were two expressions.
        stun_pct = stun_percent(situation.actor)
        target = situation.enemies[0] if situation.enemies else None
        target_id = target.id if target else None
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Actor at {stun_pct}% STUN with ranged attack "
                f"({best.name}, {best.damage_dice}d6). "
                "Current position has been compromised — enemies are "
                "targeting this location. Reposition to a new cover "
                "spot to reset the range advantage."
            ),
            steps=[
                PlanStep(
                    kind="move_to_cover",
                    notes=(
                        
                        "CRITICAL: choose a DIFFERENT cover position than "
                        "your current one — move to break the enemy's "
                        "current targeting line. Prioritise positions "
                        "that provide a new angle on the fight."
                    ),
                    params={
                        "prefer_cover": True,
                        "change_position": True,
                        "break_targeting_line": True,
                    },
                ),
                PlanStep(
                    kind="attack",
                    target_id=target_id,
                    power_xmlid=best.xmlid,
                    notes=(
                        "Fire from the new cover position. "
                        "The enemy must re-acquire your new location "
                        "before they can target you effectively again."
                    ),
                ),
            ],
            expected_outcome=(
                "Actor at new cover position — enemies lose previous "
                "targeting line. Actor continues ranged attack from "
                "a fresh, uncompromised firing position."
            ),
        )
