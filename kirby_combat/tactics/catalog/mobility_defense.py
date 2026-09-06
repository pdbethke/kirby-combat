"""Mobility defense — use superior movement to break line of sight.

A combatant with FLIGHT, TELEPORTATION, or high RUNNING can use their
movement advantage defensively: reposition behind cover, break LoS,
or get above attackers where ground-based melee can't follow.

Gate: actor has a FLIGHT, TELEPORTATION, or RUNNING power with levels
(i.e. the power is a purchased extra, not just base characteristic
Running). TELEPORTATION and FLIGHT are gated on presence with any
levels; RUNNING is gated on the xmlid appearing in hero.powers (meaning
purchased extra inches beyond the base 12m).

Preconditions (combatant-shaped — Situation carries no position data):
  * Actor has a FLIGHT, TELEPORTATION, or RUNNING power in hero.powers.

Gate note: HeroCombatant.attacks is the canonical source for attack
powers; hero.powers is scanned for movement powers. Scanning directly
via hero.powers xmlids matches how can_swim() and has_self_contained_
breathing() operate in HeroCombatant, and avoids circular imports with
action_enumeration._MOVEMENT_XMLIDS.

Terrain linkage:
  Narrative text describes repositioning above the fight (FLIGHT) or
  blinking to a new position (TELEPORTATION). Most effective when the
  terrain summary shows cover positions or elevated vantage points.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.catalog._filters import _MOVEMENT_XMLIDS
from kirby_combat.tactics.library import register


def _has_movement_power(situation: Situation) -> bool:
    """True if actor has any FLIGHT, TELEPORTATION, or RUNNING power.

    Scans actor.hero.powers xmlids directly (same pattern as
    HeroCombatant.can_swim / has_self_contained_breathing).
    Any levels > 0 on a FLIGHT/TELEPORTATION/RUNNING power qualifies.
    """
    for p in getattr(getattr(situation.actor, "hero", None), "powers", None) or []:
        xmlid = (getattr(p, "xmlid", "") or "").upper()
        if xmlid in _MOVEMENT_XMLIDS:
            # Any purchased movement power qualifies (levels OR base_cost > 0)
            if (getattr(p, "levels", 0) or 0) > 0 or (getattr(p, "base_cost", 0) or 0) > 0:
                return True
    return False


def _movement_power_name(situation: Situation) -> str:
    """Return the name of the actor's primary mobility power, or 'movement'."""
    for p in getattr(getattr(situation.actor, "hero", None), "powers", None) or []:
        xmlid = (getattr(p, "xmlid", "") or "").upper()
        if xmlid in _MOVEMENT_XMLIDS:
            if (getattr(p, "levels", 0) or 0) > 0 or (getattr(p, "base_cost", 0) or 0) > 0:
                return getattr(p, "name", None) or xmlid.capitalize()
    return "movement"


@register
class MobilityDefense(Tactic):
    name = "mobility_defense"
    basis = Basis(judgement="a moving target is harder to hit than a stationary one with the same DCV")
    priority = 50
    narrative_summary = (
        "Use your superior movement to break line of sight and reposition. "
        "If you have flight, go UP — most melee fighters can't follow. "
        "If you have teleportation, blink behind cover or to a flanking "
        "position before the enemy can react. "
        "Combine movement with a ranged attack on the same phase: "
        "move first, shoot from the new position. "
        "Never stay in one place so long that enemies can bracket you."
    )

    def applicable(self, situation: Situation) -> bool:
        return _has_movement_power(situation)

    def execute(self, situation: Situation) -> Plan:
        move_name = _movement_power_name(situation)
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Actor has {move_name} — superior movement enables breaking "
                "LoS, repositioning to cover, or escaping melee threat. "
                "Movement advantage converts into defensive distance."
            ),
            steps=[
                PlanStep(
                    kind="move",
                    notes=(
                        f"Use {move_name} to reposition. Priority order: "
                        "1) break current LoS if being targeted, "
                        "2) move to elevated position or behind cover, "
                        "3) flank to gain positional advantage. "
                        "Use remaining action for a ranged attack from the "
                        "new position if a target is in range."
                    ),
                    params={
                        "use_movement_power": True,
                        "prefer_cover": True,
                        "break_los": True,
                    },
                ),
            ],
            expected_outcome=(
                "Actor breaks current targeting, gains cover or elevation, "
                "and maintains offensive threat from a new position."
            ),
        )
