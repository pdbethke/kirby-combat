"""Get out --- when you cannot reach them and they can reach you.

THE CASE THIS EXISTS FOR. Ike Clanton stood in the lot beside Fly's with
no gun while four armed men shot at each other around him. Wyatt told him
he was unarmed and let him go, and he ran. Billy Claiborne ran with him.
Both survived the most famous gunfight in the West by leaving it.

Simulated, they stayed --- punching armed men for 0 STUN a Phase until
they were shot --- because the catalogue had twenty tactics and every one
of them was a way to keep fighting. There was no doctrine of leaving,
and until `disengage` existed there was no action for it either.

THE GATE IS DELIBERATELY NARROW, and it is a fact rather than a mood: the
actor has NOTHING TO FIGHT WITH, while an enemy has something that
reaches him. Not "losing", not "outnumbered", not "hurt" ---
`take_cover_when_hurt` already owns hurt, and a wounded fighter who can
still shoot has a better option than running.

It used to compare REACH alone --- mine doubled still short of theirs ---
and that was wrong in a way one fight made obvious. Power Lad, 399.5
points with a 6d6 killing attack and armor no revolver can scratch, was
dropped into this lot and ran on his first Phase: his fists reach a metre
and their guns reach forty. Range is not distance. A 40m revolver says
nothing about where its owner is standing, and in this lot everyone was
two metres apart, so no geometric patch fixes it either.

Being outranged was never the trouble. Ike had no gun. That is the fact
this gate now reads, and it is the one the paragraph above always
described.

WHAT THIS GIVES UP, on purpose: an armed-but-outranged fighter --- a knife
against a rifle across a field --- no longer gets this tactic. That case
wants a doctrine about CLOSING rather than leaving, and inventing one here
on the strength of a single gunfight would be guessing. This tactic is
`judgement` basis, not RAW, so it should claim only what it can defend.

Priority sits above the attack tactics and below `take_cover_when_hurt`:
cover is the cheaper answer when there is cover, and running is what you
do when nothing you have can reach the fight.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register


def _longest_reach(combatant) -> float:
    """The furthest this fighter can hurt anybody, in metres.

    A melee-only fighter's reach is `reach_m`; a gun's is `range_m`.
    Reading the max over both means an unarmed man scores about a metre
    and a rifleman scores a hundred, which is the comparison that
    matters.
    """
    best = 0.0
    for attack in getattr(combatant, "attacks", None) or []:
        best = max(best, float(getattr(attack, "range_m", 0.0) or 0.0),
                   float(getattr(attack, "reach_m", 0.0) or 0.0))
    return best


@register
class WithdrawWhenOutmatched(Tactic):
    name = "withdraw_when_outmatched"
    basis = Basis(
        judgement="a fighter who cannot reach the enemy is not fighting, "
                  "only waiting to be hit",
    )
    priority = 54
    narrative_summary = (
        "You have nothing that can reach them and they have something "
        "that reaches you. Standing here spends Phases achieving nothing "
        "while they shoot. Break off and get clear -- leaving the field "
        "ends your part in the fight, which is a better outcome than "
        "being shot in it."
    )

    def applicable(self, situation: Situation) -> bool:
        enemies = [e for e in (situation.enemies or [])]
        if not enemies:
            return False
        # Nothing to fight with -- not "outreached", which is a different
        # and much larger claim. A fighter holding anything at all has a
        # choice to make that this tactic is not qualified to make for him.
        if getattr(situation.actor, "attacks", None):
            return False
        theirs = max((_longest_reach(e) for e in enemies), default=0.0)
        return theirs > 0.0

    def execute(self, situation: Situation) -> Plan:
        mine = _longest_reach(situation.actor)
        theirs = max(
            (_longest_reach(e) for e in (situation.enemies or [])), default=0.0,
        )
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Actor reaches {mine:.0f}m; the enemy reaches {theirs:.0f}m. "
                "Nothing the actor has can touch them, so every Phase spent "
                "here is a Phase spent being shot at for free."
            ),
            steps=[
                PlanStep(
                    kind="disengage",
                    notes=(
                        "Full Move directly away from the enemies' centroid. "
                        "Leaving the field ends this fighter's part in the "
                        "fight."
                    ),
                ),
            ],
            expected_outcome=(
                "Actor opens the range and, on leaving the field, stops "
                "being a target."
            ),
        )
