"""Go around the wall instead of trying to knock it down.

PeterB, shown five men shooting at a boarding house: "why not just go
around the building".

BECAUSE NOTHING COULD ASK. `reposition_strike` --- spend a half-move
reaching a vantage with a clear line of fire, then shoot --- is fully
built and has been for a long time: enumeration offers it, a resolver
resolves it, and the destination is precomputed by
`nearest_visible_point` so nothing recomputes geometry. It is offered on
exactly the condition that matters here, an enemy whose `perceive` result
is `occluded`.

NOT ONE OF THE TWENTY-FOUR TACTICS EVER NAMED THAT KIND. The whole
subsystem was reachable only by a chooser that invented the action id
itself. So when Virgil Earp stood behind Fly's Studio where no Cowboy
could see him, the doctrine layer's entire answer was `smash_cover` ---
break the building --- and when that produced an unexecutable plan,
everyone fell through to the fallback and shot the scenery.

Flanking outranks demolition (priority 37 against 35) for the ordinary
reason: walking round the end of a wall is cheaper than making a hole in
it, and it leaves you somewhere better rather than somewhere louder.
`smash_cover` remains the answer when there is no way around --- and now
that a breached wall is a hole you can shoot through rather than a
demolished building, the two are genuinely different plans instead of one
good one and one absurd one.

THE ENGINE DECIDES WHETHER IT IS POSSIBLE, not this. A tactic cannot see
the menu; enumeration has already asked whether any movement mode reaches
a line-of-sight-clear vantage within a half-move, and offers nothing when
none does. So this names the move and the man, and a fight where the wall
cannot be flanked simply falls through to the next tactic --- which is
the right answer, and is `smash_cover`.
"""
from __future__ import annotations

from typing import Any

from kirby_combat.perception import perceive
from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register


def _occluded_enemy(situation: Situation) -> Any | None:
    """The first enemy a wall is standing between us and.

    The same question `smash_cover` asks, from the other end: it wants the
    wall, this wants the man.
    """
    session = getattr(situation, "session", None)
    scene = getattr(session, "scene", None)
    if scene is None:
        return None
    for enemy in situation.enemies:
        if perceive(situation.actor, enemy, scene).occluder_id:
            return enemy
    return None


def _best_ranged(situation: Situation):
    """You reposition to restore a LINE OF FIRE, so this wants a ranged
    attack --- the same one enumeration builds the offer around."""
    ranged = [a for a in getattr(situation.actor, "attacks", [])
              if (a.damage_dice or 0) > 0 and getattr(a, "is_ranged", False)]
    return max(ranged, key=lambda a: a.damage_dice) if ranged else None


@register
class GoAroundTheCover(Tactic):
    name = "go_around_the_cover"
    basis = Basis(
        judgement="a wall you cannot see past is worth walking around before "
                  "it is worth breaking",
    )
    priority = 37
    narrative_summary = (
        "An enemy is behind a wall you cannot shoot through. Move to a "
        "vantage where the line of fire is clear and shoot from there, "
        "rather than spending phases breaking the wall down."
    )

    def applicable(self, situation: Situation) -> bool:
        return (_occluded_enemy(situation) is not None
                and _best_ranged(situation) is not None)

    def execute(self, situation: Situation) -> Plan:
        target = _occluded_enemy(situation)
        best = _best_ranged(situation)
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"A wall stands between you and "
                f"{getattr(target, 'id', 'the enemy')}, so there is no shot "
                f"from here. Move to a vantage with a clear line of fire and "
                f"shoot from there with {getattr(best, 'name', 'your best gun')} "
                f"-- cheaper than breaking the wall, and it ends with you "
                f"somewhere better."
            ),
            steps=[
                PlanStep(
                    # The composite: a half-move to a clear vantage, then
                    # fire. Enumeration has already checked a movement mode
                    # can reach one; when none can, there is no offer and
                    # the chooser falls through to `smash_cover`.
                    kind="reposition_strike",
                    target_id=getattr(target, "id", None),
                    power_xmlid=getattr(best, "xmlid", None),
                    notes="Move to where the shot exists, then take it.",
                ),
            ],
            expected_outcome=(
                "A clear line of fire on a man who thought he was behind "
                "cover, without spending a phase on masonry."
            ),
        )
