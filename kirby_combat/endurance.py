"""What a power costs to use (6E1 p.132).

NOBODY IN THIS ENGINE HAD EVER SPENT END ON AN ATTACK. `actions/base.py`
computed `end_spent = max(1, power.damage_dice)`, put it on the
`AttackResult`, and no caller subtracted it --- so a fighter threw an 8d6
Blast and finished the Phase at the END he started with, while the engine
implemented Recovery, Post-Segment 12 Recovery and a REC characteristic
with nothing to recover from.

THE RULE, quoted. 6E1 p.132: "Every Phase such a Power is turned on, it
costs the character 1 END for every 10 Active Points of Power used ...
The minimum END cost for a power that costs END is 1 END per Phase,
regardless of how few Active Points of the Power a character uses." And
the rounding, with the book's own two examples: "The standard rounding
rules apply to END cost calculations. A character using a 15 Active Point
ability pays 1 END; a character using a 46 Active Point ability pays 5
END."

15 -> 1 is the half rounding DOWN, because HERO rounds in the character's
favour and this is a cost. 46 -> 5 is 4.6 rounding up. Both are tests.

ACTIVE POINTS, NOT DICE. The old proxy read the dice count, which is
roughly double: an 8d6 Blast is 40 Active Points and costs 4 END, not 8.
`AttackPower.active_points` has carried the cost engine's own figure since
`hero_view` line 992 and nothing used it for this.

WHAT IS FREE. A power on Charges, and one bought with Reduced Endurance
(0 END). `hero_view` line 1933 has been parsing the second for a long time
and throwing it away, with the comment `# noqa: F841 (END calc TBD)`.
That is why the O.K. Corral was the wrong place to notice the missing
spend: a Colt Peacemaker runs on Charges, so those nine men were right to
end the fight at full END.

NO ACTIVE POINTS IS NOT FREE. A hand-built power with no cost-engine
figure costs the minimum, because returning 0 would make every synthetic
fixture in the suite a perpetual-motion machine.
"""
from __future__ import annotations

from typing import Any

#: 6E1 p.132. One END per ten Active Points.
ACTIVE_POINTS_PER_END = 10

#: "The minimum END cost for a power that costs END is 1 END per Phase."
MINIMUM_END = 1


def costs_end(power: Any) -> bool:
    """Whether using this power costs the character anything at all.

    Charges and Reduced Endurance (0 END) are the two ways an attack in
    this engine is free. Both are read off the build; neither is inferred
    from the shape of the power.
    """
    if getattr(power, "reduced_end", False):
        return False
    charges = getattr(power, "charges", None)
    # NONE IS NOT ZERO, the same distinction `charges.charges_on` draws:
    # "unlimited" and "has a clip" must never be the same answer.
    return charges is None


def end_cost(power: Any) -> int:
    """END this power costs for one Phase's use (6E1 p.132)."""
    if not costs_end(power):
        return 0
    active = int(getattr(power, "active_points", 0) or 0)
    if active <= 0:
        return MINIMUM_END
    # HERO rounds to nearest and gives the half to the character. This is
    # a cost, so the half rounds DOWN -- which is the book's own 15 -> 1.
    whole, remainder = divmod(active, ACTIVE_POINTS_PER_END)
    cost = whole + (1 if remainder * 2 > ACTIVE_POINTS_PER_END else 0)
    return max(MINIMUM_END, cost)
