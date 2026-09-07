"""Reposition when spotted — sniper defensive: move to new cover when hurt.

A ranged combatant who has taken damage in their current position has
been spotted. Their cover advantage is compromised and enemies are
now zeroing in. The correct play is to immediately reposition to a
new cover position before taking more fire — then continue shooting
from the new location.

Preconditions:
  * Actor health is NOT at the "default" state (STUN < 50% of max
    OR BODY ≤ 0). Mirrors ``take_cover_when_hurt``'s health check —
    both use the same ``_classify_health``-equivalent thresholds.
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

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.catalog._filters import _best_ranged_attack
from kirby_combat.tactics.library import register

# Health thresholds — mirrors situation_builder._classify_health.
_STUN_WOUNDED_PCT = 50
_STUN_CRITICAL_PCT = 25


def _health_is_not_default(situation: Situation) -> bool:
    actor = situation.actor
    max_stun = actor.max_stun
    if max_stun <= 0:
        return False
    stun_pct = round(100 * actor.current_stun / max_stun)
    body_pct = round(100 * actor.current_body / max(actor.max_body, 1))
    if body_pct <= 0 or stun_pct <= _STUN_CRITICAL_PCT:
        return True
    return stun_pct < _STUN_WOUNDED_PCT


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
        if not _health_is_not_default(situation):
            return False
        return _best_ranged_attack(situation) is not None

    def execute(self, situation: Situation) -> Plan:
        best = _best_ranged_attack(situation)
        stun_pct = round(
            100 * situation.actor.current_stun
            / max(situation.actor.max_stun, 1)
        )
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
