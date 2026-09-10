"""What SHAPE the enemy is in — the thing the page never said.

A point-of-view render of one moment was shown to a vision model, which
reported four things about it: six figures, solid walls on both flanks,
open ground between, and "they are tightly bunched together".

Three of those the Brief already says, more precisely. The fourth it
never said at all. Its "Where they are" section is a list of individual
bearings --- exact, and silent about the shape:

    The Kid:    46.0m, -6 OCV at that range, cover 2/4
    Rell Hoyt:  46.3m, -6 OCV at that range
    Beck:       49.2m, -6 OCV at that range, cover 2/4

"Bunched" is what makes an Area Of Effect, a Sweep or a group Presence
Attack worth a Phase, and it is exactly what a picture gives away for
free and a list of distances does not.

THE THRESHOLD IS THE BOOK'S, NOT A FEEL. 6E1 p.322: the cheapest Area Of
Effect (Radius) a character can buy, at +1/4, "can define a power's Radius
as anything up to 4m", doubling per further quarter. A 4m radius spans
8m, so a group whose widest gap is under that is one an ordinary,
cheaply-bought area attack could catch several of. That is the question
the line exists to answer.

WIDEST GAP, NOT AVERAGE. An average hides a straggler: four men in a knot
and a fifth forty metres off average out as tight, and an area attack
aimed at the knot does not reach him.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Formation:
    """How a group of combatants is arranged, as one fact."""

    #: 6E1 p.322 --- the span of the cheapest Area Of Effect radius.
    BUNCHED_WITHIN_M = 8.0

    count: int
    #: The widest distance between any two of them, in metres.
    spread_m: float

    @property
    def is_bunched(self) -> bool:
        return self.spread_m <= self.BUNCHED_WITHIN_M

    def render(self) -> str:
        """One line for the page.

        Both answers earn their place: "bunched" is the reason to spend a
        Phase on an area attack, and "spread" is the reason not to.
        """
        if self.is_bunched:
            return (f"They are BUNCHED: all {self.count} within "
                    f"{self.spread_m:.0f}m of each other — one Area Of Effect, "
                    f"Sweep or group Presence Attack could reach several")
        return (f"They are spread out: {self.count} of them across "
                f"{self.spread_m:.0f}m — an area attack would catch one at a time")


def formation_of(positions) -> Formation | None:
    """The shape of these positions, or None when there is no shape.

    One man is not a formation and "bunched" about him is nonsense; nor is
    an empty field. None is a real answer and the caller prints nothing.
    """
    points = [p for p in positions if p is not None]
    if len(points) < 2:
        return None
    spread = max(
        math.dist((a.x, a.y, getattr(a, "z", 0.0) or 0.0),
                  (b.x, b.y, getattr(b, "z", 0.0) or 0.0))
        for a, b in itertools.combinations(points, 2)
    )
    return Formation(count=len(points), spread_m=spread)
