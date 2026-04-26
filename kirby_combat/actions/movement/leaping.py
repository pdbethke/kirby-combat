"""Leaping — 6E default 4" jump (1 END/10m, NCM 4×).

Vertical distance = 1/2 horizontal distance per RAW; that constraint is left
to higher-layer logic when it cares.
"""
from __future__ import annotations

from kirby_combat.actions.movement.base import MovementAction


class Leaping:
    """Factory for Leaping movement actions."""

    name: str = "leaping"

    @classmethod
    def make(
        cls,
        distance_m: float,
        move_type: str,
        base_inches: int,
    ) -> MovementAction:
        return MovementAction(
            name=cls.name,
            distance_m=distance_m,
            move_type=move_type,
            base_inches=base_inches,
            end_per_10m=1,
            noncombat_multiplier=4,
        )
