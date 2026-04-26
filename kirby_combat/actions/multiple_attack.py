"""Multiple Attack — multiple swings against multiple targets in one phase.

HERO 6E2 pg 73:
- Each attack after the first takes a cumulative -2 OCV
- ½ DCV per 6E2 p79 §DCV Modifiers
- Full-phase action
- CSL offset (Combat Skill Levels allocated to OCV) flattens the descending
  penalty: per_shot_ocv[i] = base_ocv - max(0, (2*i) - csl_offset)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class MultiAttackOutcome:
    per_shot_ocv: list[int]
    dcv_factor: float
    dc_per_shot_bonus: int
    phase_cost: Literal["half", "full"]


class MultipleAttack:
    name: str = "multiple_attack"

    @staticmethod
    def compute(
        base_ocv: int,
        num_targets: int,
        csl_offset: int = 0,
    ) -> MultiAttackOutcome:
        if num_targets < 1:
            raise ValueError("num_targets must be >= 1")
        ocvs = [base_ocv - max(0, (2 * i) - csl_offset) for i in range(num_targets)]
        return MultiAttackOutcome(
            per_shot_ocv=ocvs,
            dcv_factor=0.5,
            dc_per_shot_bonus=0,
            phase_cost="full",
        )
