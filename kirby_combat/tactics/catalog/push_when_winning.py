"""Push when winning — PUSH attacks for extra DCs when END headroom allows.

A combatant who still has END reserves can declare a PUSH on any
attack, spending +5 END per +1 DC added.  This is
most effective when ahead in the fight and the extra die could KO or
stun the target before they act.

Preconditions:
  * Actor's current_end > 60% of max_end (enough headroom to PUSH
    without immediately exhausting themselves).
  * Actor has at least one damaging attack to PUSH.

Terrain linkage:
  Primarily a tactical meta-decision.  The chooser should note when the
  actor has END headroom and an enemy who is near the STUN threshold,
  and suggest the PUSH modifier on the next attack.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.catalog._filters import _best_attack
from kirby_combat.tactics.library import register

_END_HEADROOM_FRACTION = 0.6  # must exceed this fraction


def _has_damaging_attack(situation: Situation) -> bool:
    return any(
        (a.damage_dice or 0) > 0
        for a in getattr(situation.actor, "attacks", [])
    )


def _has_end_headroom(situation: Situation) -> bool:
    max_end = situation.actor.max_end
    if max_end <= 0:
        return False
    return situation.actor.current_end > max_end * _END_HEADROOM_FRACTION


@register
class PushWhenWinning(Tactic):
    name = "push_when_winning"
    basis = Basis(mechanism="6E2 p133", doctrine="6E2 p39")
    priority = 33
    narrative_summary = (
        "You have END headroom — now is the time to PUSH. "
        "Declare PUSH on your next attack to add +1 DC for extra END cost. "
        "Use it when the target is near their STUN threshold "
        "and one bigger hit could stun or KO them this phase. "
        "Don't wait until you're END-drained — PUSH while you have the "
        "reserves to do it. One PUSH at the right moment ends the fight faster."
    )

    def applicable(self, situation: Situation) -> bool:
        return _has_end_headroom(situation) and _has_damaging_attack(situation)

    def execute(self, situation: Situation) -> Plan:
        best = _best_attack(situation)
        target = (situation.enemies[0] if situation.enemies else None)
        target_id = target.id if target else None
        end_pct = int(
            100 * situation.actor.current_end / max(situation.actor.max_end, 1)
        )
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Actor at {end_pct}% END (above 60% threshold). "
                f"PUSHING {best.name} ({best.damage_dice}d6) adds +1 DC "
                "for the cost of extra END — a good trade while ahead."
            ),
            steps=[
                PlanStep(
                    kind="attack",
                    target_id=target_id,
                    power_xmlid=best.xmlid,
                    notes=(
                        "Declare PUSH modifier on this attack. "
                        "Best used when the target is near STUN threshold "
                        "and the extra die would tip the KO."
                    ),
                    params={"push": True},
                ),
            ],
            expected_outcome=(
                f"PUSH adds +1 DC to {best.damage_dice}d6 at extra END cost. "
                "Trade favourable while above 60% END."
            ),
        )
