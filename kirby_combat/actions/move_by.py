"""Move-By — velocity-based half-phase attack while moving past target.

HERO 6E2 pg 70:
- Damage DC = STR_DC + floor(velocity_m / 10), where STR_DC = floor(STR / 5)
- Attacker: -2 OCV, -2 DCV
- Half-phase action; attacker continues moving past target
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


@dataclass
class MoveByOutcome:
    damage_dc: int
    ocv_modifier: int                         # always -2 for Move-By
    dcv_modifier: int                         # always -2 for Move-By
    phase_cost: Literal["half", "full"]       # "half" for Move-By
    distance_past_target_m: float = 0.0       # 0 unless caller supplies movement context


class MoveBy:
    """Compute Move-By attack parameters."""

    name: str = "move_by"

    @staticmethod
    def compute(
        attacker_str: int,
        velocity_mps: float,
        total_movement_m: float | None = None,
        distance_to_target_m: float | None = None,
    ) -> MoveByOutcome:
        """Compute Move-By attack DC and modifiers.

        Required:
            attacker_str   — attacker's STR (used to compute STR_DC = STR/5).
            velocity_mps   — attacker's velocity at impact, in meters per phase.

        Optional context for distance_past_target_m:
            total_movement_m       — total distance moved this phase
            distance_to_target_m   — distance from start to impact

        Returns MoveByOutcome with damage_dc, modifiers, phase_cost, and (if
        movement context provided) distance_past_target_m.
        """
        v = max(0.0, velocity_mps)
        s = max(0, attacker_str)
        str_dc = s // 5
        velocity_dc = math.floor(v / 10.0)
        damage_dc = str_dc + velocity_dc

        distance_past = 0.0
        if total_movement_m is not None and distance_to_target_m is not None:
            distance_past = max(0.0, total_movement_m - distance_to_target_m)

        return MoveByOutcome(
            damage_dc=damage_dc,
            ocv_modifier=-2,
            dcv_modifier=-2,
            phase_cost="half",
            distance_past_target_m=distance_past,
        )
