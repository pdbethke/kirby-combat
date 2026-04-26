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
