"""Multiple Attack — multiple swings against multiple targets in one phase.

HERO 6E2 p.73:
- The penalty is (N-1) x -2 for N attacks, applied to EVERY Attack Roll
- 1/2 DCV per 6E2 p.79 SS DCV Modifiers
- Full-phase action
- CSL offset (Combat Skill Levels allocated to OCV) buys the penalty down,
  and cannot lift a shot above the base OCV

THE PENALTY IS FLAT, NOT A LADDER, and this file said the opposite until
2026-09-07. "Each attack after the first takes a cumulative -2" reads
naturally as shot 1 at full OCV, shot 2 at -2, shot 3 at -4. What the
page means is that the penalty ACCUMULATES WITH THE NUMBER OF ATTACKS and
is then charged on every roll in the sequence -- its three worked examples
say -8 on each of five attacks, -4 on all of three shots, -6 on all of
four. `tests/test_multiple_attack_raw.py` pins all three.

Why it mattered more than a couple of OCV points: under the ladder the
first shot of a Multiple Attack was IDENTICAL to a single attack and
every further shot was free, so the maneuver strictly dominated attacking
once. A model given the choice took it in 11 of 13 Phases of the O.K.
Corral, and was right to. The flat penalty is what makes it a choice.
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
        # (N-1) x -2, bought down by levels, never lifting above the base.
        penalty = max(0, 2 * (num_targets - 1) - csl_offset)
        ocvs = [base_ocv - penalty] * num_targets
        return MultiAttackOutcome(
            per_shot_ocv=ocvs,
            dcv_factor=0.5,
            dc_per_shot_bonus=0,
            phase_cost="full",
        )
