"""Autofire — power Advantage; weapon fires multiple shots per phase.

HERO 6E1 pg 281:
- Default 5 shots per phase (configurable per power)
- -2 cumulative OCV per shot beyond first
- DCV unchanged (autofire is a power feature, not a phase-spending stance)
- Full-phase action
"""
from __future__ import annotations

from kirby_combat.actions.multiple_attack import MultiAttackOutcome


class Autofire:
    name: str = "autofire"

    @staticmethod
    def compute(
        base_ocv: int,
        num_shots: int = 5,
        csl_offset: int = 0,
    ) -> MultiAttackOutcome:
        if num_shots < 1:
            raise ValueError("num_shots must be >= 1")
        ocvs = [base_ocv - max(0, (2 * i) - csl_offset) for i in range(num_shots)]
        return MultiAttackOutcome(
            per_shot_ocv=ocvs,
            dcv_factor=1.0,
            dc_per_shot_bonus=0,
            phase_cost="full",
        )
