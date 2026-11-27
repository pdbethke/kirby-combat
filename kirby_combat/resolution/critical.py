"""Critical Hits (6E2 p.120), an optional rule (`CombatTemplate.use_critical_hits`).

"A 'critical hit' is a blow so accurate it does maximum damage. One occurs
when a character's roll to hit is less than half of what he needed to hit
the target." Needing 12, he must roll under 6; needing 13, under 6.5. So
the test is ``2 * roll < needed``, which keeps the half exact.

"Characters may only do critical hits to living targets. Ignore critical
hit results against targets like doors and walls (it would be far too
easy to get a critical hit on a DCV 0 door)." An object is a `Breakable`.

Maximum damage is every damage die and the STUN Multiplier die at its top
face, so the one damage procedure the hit already goes through
(`resolution/damage.py`, then Hit Locations) does the rest: with Hit
Locations a Killing Attack's STUN is the location's STUNx on the maximum
BODY, exactly as the page says, because the location is applied after.

Western Hero p.153 also makes a natural 3 critical; 6E2 does not, and this
follows 6E2. Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from kirby_combat.models import DiceValues

#: The top face of the d6 every damage and STUN Multiplier die is rolled on.
TOP_FACE = 6


def is_critical(*, roll: int, needed: int) -> bool:
    """Whether a roll of ``roll`` against ``needed`` or less is under half."""
    return 2 * int(roll) < int(needed)


def is_living(target: Any) -> bool:
    from kirby_combat.participant import Breakable

    return not isinstance(target, Breakable)


def maximum(dice: DiceValues) -> DiceValues:
    """The same dice, every damage die and STUN Multiplier die at its top."""
    return replace(dice, damage=[TOP_FACE] * len(dice.damage),
                   stun_multiplier=[TOP_FACE] * max(1, len(dice.stun_multiplier)))
