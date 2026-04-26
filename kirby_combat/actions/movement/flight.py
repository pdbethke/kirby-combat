"""Flight — 3D movement; treats walls/terrain as ignorable at engine layer.

Scene-aware logic (obstacles, movement terrain, ceiling height) is left to
Task 20 (Scene integration). 1 END/10m, NCM 4×.
"""
from __future__ import annotations

from kirby_combat.actions.movement.base import MovementAction


class Flight:
    """Factory for Flight movement actions."""

    name: str = "flight"

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
