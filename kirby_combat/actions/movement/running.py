"""Running — 6E default ground movement (1 END/10m, NCM 4×)."""
from __future__ import annotations

from kirby_combat.actions.movement.base import MovementAction


class Running:
    """Factory for Running movement actions."""

    name: str = "running"

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
