"""Rapid Fire — multiple ranged attacks against one or more targets in one phase.

HERO 6E2 pg 75:
- Same -2 cumulative OCV per shot, 1/2 DCV
- Optional: +1 DC per shot above the first (paid in extra END)
- Full-phase action
"""
from __future__ import annotations

from kirby_combat.actions.multiple_attack import MultiAttackOutcome


class RapidFire:
    name: str = "rapid_fire"

    @staticmethod
    def compute(
        base_ocv: int,
        num_shots: int,
        csl_offset: int = 0,
        extra_dc_per_shot: bool = False,
    ) -> MultiAttackOutcome:
        if num_shots < 1:
            raise ValueError("num_shots must be >= 1")
        ocvs = [base_ocv - max(0, (2 * i) - csl_offset) for i in range(num_shots)]
        return MultiAttackOutcome(
            per_shot_ocv=ocvs,
            dcv_factor=0.5,
            dc_per_shot_bonus=1 if extra_dc_per_shot else 0,
            phase_cost="full",
        )
