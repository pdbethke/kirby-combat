"""Tunneling — slow movement that creates a dug trail.

RAW: cannot be done at noncombat rate (you tunnel at a constant speed).
Material DEF gating is Scene-aware and not yet wired in here. 1 END/10m,
NCM 1× (noncombat speedup does not apply).
"""
from __future__ import annotations

from kirby_combat.actions.movement.base import MovementAction


class Tunneling:
    """Factory for Tunneling movement actions."""

    name: str = "tunneling"

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
            noncombat_multiplier=1,
        )
