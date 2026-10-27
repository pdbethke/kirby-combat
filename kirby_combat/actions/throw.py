"""Throw — pure-math distance + damage for throwing a grabbed target.

Per 6E1 §STRENGTH TABLE / §THROWING TABLE (and 6E2 p87 for the maneuver):
    - Half-phase action by the thrower (must already have grab on target).
    - Max throw distance scales NON-LINEARLY with STR per the
      published STR/THROWING TABLE — STR 50 throws ~64m, STR 100
      throws ~144m. Linear STR/5 is a 5E approximation that
      drastically undersells superhero-tier brick STR.
    - Damage: STR_DC dice of normal damage (STR_DC = floor(STR / 5)).

This file encodes the Throw distance for a NEGLIGIBLE-mass object
(approximated as 1kg or less) per the table values. Heavier objects
fly less far; the engine does NOT yet model object-weight scaling
(future work — feed via the ImpactTarget weight when available).

Caller may specify desired_distance_m (clamped to [0, max]).

NOTE: Distance values are RAW-approximate; cross-check against
published character-sheet throw examples before relying on exact
distances. The table follows the 6E STR-table progression but
absolute meters are interpolated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# Per 6E1 §STR/THROWING TABLE (approximation):
# Distance for a negligible-mass object (1kg or less). Each tuple is
# (STR threshold, max throw distance in meters). The throw distance for
# a given STR uses the entry whose threshold is the highest one ≤ STR.
_THROW_DISTANCE_TABLE: list[tuple[int, int]] = [
    (0, 0),
    (5, 8), (10, 16), (15, 16), (20, 32), (25, 32),
    (30, 40), (35, 56), (40, 56), (45, 64), (50, 64),
    (55, 80), (60, 80), (70, 96), (80, 112), (100, 144),
]


def _max_throw_distance_m(strength: int) -> float:
    """Throw distance for a 1kg object, per 6E1 STR/THROWING TABLE (approx).

    Args:
        strength: Attacker's STR.

    Returns:
        Maximum throw distance in meters (linear-step lookup; the highest
        STR threshold ≤ strength wins). For STR > 100 we extrapolate
        +16m per +20 STR above 100 (rough continuation of the table).
    """
    s = max(0, strength)
    if s >= 100:
        # Rough extrapolation above the published-table top.
        return 144.0 + ((s - 100) // 20) * 16.0
    last = 0.0
    for threshold, dist in _THROW_DISTANCE_TABLE:
        if s >= threshold:
            last = float(dist)
        else:
            break
    return last


@dataclass
class ThrowOutcome:
    damage_dc: int
    throw_distance_m: float
    max_distance_m: float
    phase_cost: Literal["half", "full"]


class Throw:
    name: str = "throw"

    @staticmethod
    def compute(
        attacker_str: int,
        desired_distance_m: float | None = None,
    ) -> ThrowOutcome:
        """Compute throw distance and damage. If desired_distance_m is None,
        throw is at maximum range. Negative or excessive distances are clamped
        to [0, max].
        """
        s = max(0, attacker_str)
        max_dist = _max_throw_distance_m(s)
        if desired_distance_m is None:
            actual = max_dist
        else:
            actual = max(0.0, min(float(desired_distance_m), max_dist))
        return ThrowOutcome(
            damage_dc=s // 5,
            throw_distance_m=actual,
            max_distance_m=max_dist,
            phase_cost="half",
        )


def resolve_object_throw(
    thrower_str: int,
    pd: int,
    body: int,
    damage_type: str = "normal",
) -> tuple[int, str]:
    """Thrown-object damage (6E2 p82): the thrower's STR damage dice capped by
    the object's PD + BODY.  blunt → normal, sharp → killing (caller sets damage_type).

    STR damage dice = STR // 5.  The cap is max(0, pd + body) so a 0/0 object
    yields 0 dice regardless of STR.

    Args:
        thrower_str: Attacker's STR characteristic.
        pd:          Object's PD (physical defence / hardness).
        body:        Object's BODY (structural toughness).
        damage_type: "normal" for blunt objects, "killing" for sharp/edged.

    Returns:
        (damage_dice, damage_type) — the number of dice to roll and the type
        string to pass to the attack resolver.
    """
    str_dice = max(0, int(thrower_str) // 5)
    cap = max(0, int(pd) + int(body))
    return (min(str_dice, cap), damage_type)


# ---------------------------------------------------------------------------
# Throwing a CHARACTER (6E2 p.83-85)
# ---------------------------------------------------------------------------

#: 6E2 p.83's Throwing Table, the STANDING THROW column: extra STR -> metres.
#: Read off the page row by row. A Grab-and-Throw "is a Standing Throw,
#: unless the Grabber begins a Phase with a Grabbed victim and the GM lets
#: him move before making the Throw" (6E2 p.64).
STANDING_THROW_M: tuple[tuple[int, float], ...] = (
    (1, 1.0), (2, 1.5), (3, 2.0), (4, 3.0), (5, 4.0), (6, 5.0), (7, 5.5),
    (8, 6.0), (9, 7.0), (10, 8.0), (11, 9.0), (12, 9.5), (13, 10.0),
    (14, 11.0), (15, 12.0), (16, 13.0), (17, 13.5), (18, 14.0), (19, 15.0),
    (20, 16.0), (23, 18.0), (25, 20.0), (28, 22.0), (30, 24.0), (35, 28.0),
    (40, 32.0), (45, 36.0), (50, 40.0), (55, 44.0), (60, 48.0), (65, 52.0),
    (70, 56.0), (75, 60.0), (80, 64.0), (85, 68.0), (90, 72.0), (100, 80.0),
)

#: The STR it takes to lift a man. 6E2 p.119 takes "'normal' being 100
#: kilograms", and the Strength Table (6E1 p.43) lifts 100kg at STR 10.
#: RULING: every character weighs the normal 100kg -- the engine carries no
#: mass (Density Increase, Growth and Shrinking are not read here).
STR_TO_LIFT_A_MAN = 10


def standing_throw_distance_m(thrower_str: int) -> float:
    """How far a man of ``thrower_str`` throws another man (6E2 p.83).

    "Compare the character's STR to the STR necessary for the character to
    pick up the object ... the result is the 'Extra Strength' used with the
    accompanying Throwing Table." A row between two of the table's is read
    at the lower one (RULING: the page lists rows, not a formula). Above
    100 extra STR the table's own step from 45 upward, +4m per +5 STR, is
    continued (RULING). No extra STR is no distance: he is thrown down where
    he stands.
    """
    extra = int(thrower_str) - STR_TO_LIFT_A_MAN
    if extra < 1:
        return 0.0
    if extra > 100:
        return 80.0 + ((extra - 100) // 5) * 4.0
    best = 0.0
    for row, metres in STANDING_THROW_M:
        if extra >= row:
            best = metres
        else:
            break
    return best
