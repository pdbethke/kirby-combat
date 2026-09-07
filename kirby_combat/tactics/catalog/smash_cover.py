"""Smash destructible cover screening enemies.

When an actor has a damaging attack, the right play against entrenched
enemies is to destroy the cover they hide behind.  A DEF-6 stone wall
or a DEF-3 wooden barrier becomes rubble in 1-2 phases — then the
enemy stands exposed.

Preconditions:
  * Actor has at least one attack with damage_dice > 0.

Terrain linkage:
  The ``attack:construct`` and rapid-fire-vs-construct offers generated
  by the action enumeration layer are the concrete expression of this
  advice. This tactic's narrative text signals the chooser to prefer those
  menu entries when they appear.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register


def _best_damaging_attack(situation: Situation):
    """Return the attack with the highest damage_dice, or None."""
    attacks = getattr(situation.actor, "attacks", [])
    damaging = [a for a in attacks if (a.damage_dice or 0) > 0]
    if not damaging:
        return None
    return max(damaging, key=lambda a: a.damage_dice)


@register
class SmashCover(Tactic):
    name = "smash_cover"
    basis = Basis(judgement="cover the enemy is using is worth more destroyed than ignored")
    priority = 35
    narrative_summary = (
        "Target the destructible cover or barrier screening your enemy. "
        "Fire your strongest attack into the wall or obstacle — a DEF-6 "
        "stone slab crumbles in 1-2 phases, leaving them fully exposed. "
        "Use rapid-fire or the attack:construct menu option to chip it "
        "down fast. Once cover is gone the enemy has nowhere to hide."
    )

    def applicable(self, situation: Situation) -> bool:
        return _best_damaging_attack(situation) is not None

    def execute(self, situation: Situation) -> Plan:
        best = _best_damaging_attack(situation)
        target = (situation.enemies[0] if situation.enemies else None)
        target_id = target.id if target else None
        return Plan(
            tactic_name=self.name,
            rationale=(
                "Enemies are shielded by destructible cover. "
                f"Best attack ({best.name}, {best.damage_dice}d6) should "
                "focus on the cover first — removing it denies their defense "
                "and opens a clear shot next phase."
            ),
            steps=[
                PlanStep(
                    # `attack_construct` is the kind that shoots the WALL.
                    # This said kind="attack" and put "choose
                    # attack:construct" in the notes, so it shot the man
                    # instead -- an ordinary attack wearing a tactic's name.
                    kind="attack_construct",
                    target_id=target_id,
                    power_xmlid=best.xmlid,
                    notes=(
                        "Aim at the cover or barrier screening the target, "
                        "not the target."
                    ),
                    params={"prefer_construct_target": True},
                ),
            ],
            expected_outcome=(
                "Cover DEF reduced or destroyed this phase, "
                "exposing the enemy for follow-up attacks."
            ),
        )
