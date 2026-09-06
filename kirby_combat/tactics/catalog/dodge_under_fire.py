"""Dodge under fire — abort to Dodge when outnumbered by ranged attackers.

When two or more living enemies have ranged attacks, incoming fire
volume is too high to absorb. The right defensive play is to abort to
Dodge — which boosts DCV and causes ALL ranged attacks that phase to
roll against the higher value. One dodge response protects against
multiple simultaneous shooters.

Preconditions:
  * At least 2 living enemies have ranged non-mental attacks.

Terrain linkage:
  After dodging, the chooser should be nudged toward a cover
  position next phase. Dodge + move_to_cover is the ideal two-phase
  sequence when badly outnumbered. The narrative text signals this.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.catalog._filters import _MENTAL_XMLIDS
from kirby_combat.tactics.library import register

_MIN_RANGED_ENEMIES = 2  # at least this many to justify full Dodge


def _count_ranged_enemies(situation: Situation) -> int:
    """Count living enemies with at least one ranged non-mental attack."""
    count = 0
    for e in situation.enemies:
        # base.Situation documents ``enemies`` as living-only, but the
        # real caller does NOT filter KO'd combatants when it builds the
        # situation — so this skip is load-bearing.
        if e.current_stun <= 0:
            continue  # skip KO'd enemies
        for a in getattr(e, "attacks", []):
            if (
                (a.damage_dice or 0) > 0
                and a.range_m is not None
                and a.range_m > 0
                and (a.xmlid or "").upper() not in _MENTAL_XMLIDS
            ):
                count += 1
                break  # one ranged attack is enough per enemy
    return count


@register
class DodgeUnderFire(Tactic):
    name = "dodge_under_fire"
    basis = Basis(mechanism="6E2 p61", judgement="+3 DCV is worth a phase when several attackers are firing")
    priority = 52
    narrative_summary = (
        "Multiple enemies are shooting at you — abort to Dodge. "
        "A full Dodge raises your DCV against ALL ranged attacks this "
        "phase, not just one. When two or more shooters have you in "
        "their sights, a single Dodge response covers all of them. "
        "Next phase, combine a half-move to cover with a return shot "
        "so you are no longer standing in the open."
    )

    def applicable(self, situation: Situation) -> bool:
        return _count_ranged_enemies(situation) >= _MIN_RANGED_ENEMIES

    def execute(self, situation: Situation) -> Plan:
        n = _count_ranged_enemies(situation)
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"{n} living enemies have ranged attacks — incoming fire "
                "volume justifies a full Dodge to raise DCV against all of "
                "them simultaneously."
            ),
            steps=[
                PlanStep(
                    kind="wait",
                    notes=(
                        "Hold phase — be ready to abort to Dodge when an "
                        "enemy declares a ranged attack. Dodge raises DCV "
                        "until end of phase, covering all simultaneous shooters."
                    ),
                    params={"abort_to": "dodge", "trigger": "ranged_attack_declared"},
                ),
            ],
            expected_outcome=(
                "Raised DCV forces all ranged attackers to roll against "
                "the higher value. Expected: 1-2 attacks miss or deal "
                "significantly reduced damage."
            ),
        )
