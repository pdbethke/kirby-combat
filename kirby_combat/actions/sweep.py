"""Sweep — HTH variant of Multiple Attack against adjacent targets.

Same OCV math as Multiple Attack; same 1/2 DCV. The semantic difference
(adjacency requirement) is enforced by the caller via Scene checks (Task 17+).
"""
from __future__ import annotations

from kirby_combat.actions.multiple_attack import MultiAttackOutcome, MultipleAttack


class Sweep:
    name: str = "sweep"

    @staticmethod
    def compute(
        base_ocv: int,
        num_targets: int,
        csl_offset: int = 0,
    ) -> MultiAttackOutcome:
        # Identical math to Multiple Attack.
        return MultipleAttack.compute(base_ocv, num_targets, csl_offset)
