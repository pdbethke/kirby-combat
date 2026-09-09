"""Penetrating: the BODY that gets through whatever you are wearing.

READ BY NOTHING UNTIL NOW. `AttackPower.penetrating` is parsed off the
character sheet --- `hero_view._modifier_levels(power, "PENETRATING")` ---
and set on every attack, and no resolver ever looked at it, so a
Penetrating attack resolved exactly like an ordinary one. `DefenseItem
.impenetrable` was parsed and ignored the same way. A player paid points
for both.

THE MINIMUM, from the book's own worked example (6E1 p.188): "if a
character with 50% Damage Reduction is hit by an RKA 4d6, Penetrating that
does 12 BODY, 36 STUN (roll of 5, 3, 2, 2), and his defenses plus Damage
Reduction would reduce the BODY damage to 2 BODY, he takes 4 BODY - the
minimum BODY damage the Penetrating attack can cause with that roll."
Four dice, four BODY: ONE PER DIE.

A FLOOR, NOT A BONUS. The example says "he takes 4 BODY" where the
defences would have left him 2 --- the minimum replaces a smaller result
and never adds to a larger one. So this returns the floor and the caller
takes `max()`.

IMPENETRABLE ANSWERS IT, level for level (6E1 p.149): "A Defense Power
with this Advantage is particularly resistant to Penetrating attacks. An
attack with Penetrating applies normally ...; the usual 'minimum damage'
effect is ignored. Characters can buy Impenetrable multiple times to
counteract multiple purchases of Penetrating." Same shape as Hardened
against Armor Piercing, and implemented beside it for that reason.

WHOSE Impenetrable COUNTS. Hardened is explicitly per-defense --- 6E1
p.149 spends a paragraph on some defences being Hardened and others not,
which is why `defense.py` halves only the unhardened portion. The book
does not draw that distinction for Impenetrable, and it could not mean
the same thing here: a minimum is a single number applied once, not a
quantity split across items. So the target's BEST Impenetrable is the one
that answers, which is the reading that makes "buy it multiple times to
counteract multiple purchases" work.
"""
from __future__ import annotations

from typing import Any


def dice_of(power: Any) -> int:
    """How many dice this attack rolls.

    `damage_dice` is whole dice and `half_die` is the rest of it, so a
    2d6+1/2 attack rolls three. `plus_one` adds a pip to a die already
    counted and never a die of its own.
    """
    dice = int(getattr(power, "damage_dice", 0) or 0)
    if getattr(power, "half_die", False):
        dice += 1
    return max(0, dice)


def best_impenetrable(target: Any) -> int:
    """The highest Impenetrable on anything the target is wearing."""
    return max(
        (int(getattr(item, "impenetrable", 0) or 0)
         for item in (getattr(target, "defenses", None) or [])),
        default=0,
    )


def penetrating_floor(power: Any, target: Any) -> int:
    """Minimum BODY this attack does regardless of defenses, or 0.

    Zero when the attack is not Penetrating, or when the target's
    Impenetrable meets it level for level.
    """
    levels = int(getattr(power, "penetrating", 0) or 0)
    if levels <= 0:
        return 0
    if best_impenetrable(target) >= levels:
        return 0
    return dice_of(power)
