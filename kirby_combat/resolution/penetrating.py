"""Penetrating: the BODY that gets through whatever you are wearing.

READ BY NOTHING UNTIL NOW. `AttackPower.penetrating` is parsed off the
character sheet --- `hero_view._modifier_levels(power, "PENETRATING")` ---
and set on every attack, and no resolver ever looked at it, so a
Penetrating attack resolved exactly like an ordinary one. `DefenseItem
.impenetrable` was parsed and ignored the same way. A player paid points
for both.

THE MINIMUM (6E1 p.344): "no matter how high those defenses, the target
takes a minimum of 1 point of effect for every 1 'Normal Damage BODY'
rolled on the dice or the damage he'd take from the attack after applying
his defenses, whichever is greater" --- on a Normal attack's STUN, a
Killing attack's BODY, never with an AVAD. Damage Reduction cannot reduce
it (p.186, p.188: the RKA 4d6 rolling 5, 3, 2, 2 still does 4 BODY). Until
0.33 this read p.188's example as ONE BODY PER DIE on every attack, which
agrees with the book only on a roll with no 1s and no 6s, put a Normal
attack's minimum on BODY where the book puts it on STUN, and was applied
before Damage Reduction, which then cut it.

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

from dataclasses import dataclass
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


@dataclass(frozen=True)
class PenetratingMinimum:
    """The least a Penetrating hit does, whatever stopped the rest."""

    stun: int = 0
    body: int = 0


def normal_body_on(power: Any, damage_values) -> int:
    """The "Normal Damage BODY" on the dice rolled (6E1 p.344): 0 for a 1,
    1 for a 2-5, 2 for a 6; a half die 1 on a 4-6 (6E2 p.100)."""
    from kirby_combat.resolution.damage import _body_for_normal_die, half_die_body

    values = [int(v) for v in (damage_values or ())]
    half = bool(getattr(power, "half_die", False)) and values
    whole = values[:-1] if half else values
    total = sum(_body_for_normal_die(v) for v in whole)
    if half:
        total += half_die_body(values[-1])
    return total


def penetrating_minimum(power: Any, target: Any, damage_values) -> PenetratingMinimum:
    """The minimum this hit does, for the roll it made (6E1 p.344).

    "no matter how high those defenses, the target takes a minimum of 1
    point of effect for every 1 'Normal Damage BODY' rolled on the dice"
    --- on the STUN of a Normal attack, on the BODY of a Killing one (the
    book's presumption; a buyer may put it on STUN, which no sheet field
    records). Never on a Normal attack's BODY, and "It also may not be
    used with AVADs". Impenetrable ignores it level for level (p.149).

    0.32 and before floored BODY at one per DIE on every Penetrating
    attack: right for p.188's example only because 5, 3, 2, 2 is four
    Normal BODY on four dice; wrong on a 6 or a 1, and wrong for every
    Normal attack, whose minimum is STUN.
    """
    levels = int(getattr(power, "penetrating", 0) or 0)
    if levels <= 0 or best_impenetrable(target) >= levels:
        return PenetratingMinimum()
    if getattr(power, "avad", False):
        return PenetratingMinimum()
    n = normal_body_on(power, damage_values)
    if getattr(power, "damage_type", "") == "killing":
        return PenetratingMinimum(body=n)
    return PenetratingMinimum(stun=n)
