"""Throw — pure-math distance + damage for throwing a grabbed target.

HERO 6E2 pg 87:
- Half-phase action by the thrower (must already have grab on target)
- Max throw distance: attacker_str / 5 meters
- Damage: STR_DC dice of normal damage (STR_DC = floor(STR / 5))
- Caller may specify desired_distance_m (clamped to [0, max])
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


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
        max_dist = float(s / 5.0)
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
