"""Teleportation — instant 3D movement.

Costs 2 END/10m (above standard rate); no noncombat multiplier (you cannot
teleport "more inches" by moving noncombat — you teleport to where you
teleport, instant, every time).
"""
from __future__ import annotations

from kirby_combat.actions.movement.base import MovementAction


class Teleportation:
    """Factory for Teleportation movement actions."""

    name: str = "teleportation"

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
            end_per_10m=2,
            noncombat_multiplier=1,
        )
