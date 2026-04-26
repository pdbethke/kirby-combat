"""Movement actions — base class + six concrete powers.

Per HERO 6E2 pg 53, all movement supports half-move / full-move / noncombat
modes. Each concrete power is a thin factory over MovementAction with
power-specific defaults for `name`, `end_per_10m`, and `noncombat_multiplier`.
"""
from kirby_combat.actions.movement.base import MovementAction
from kirby_combat.actions.movement.running import Running
from kirby_combat.actions.movement.leaping import Leaping
from kirby_combat.actions.movement.flight import Flight
from kirby_combat.actions.movement.swimming import Swimming
from kirby_combat.actions.movement.teleportation import Teleportation
from kirby_combat.actions.movement.tunneling import Tunneling

__all__ = [
    "MovementAction",
    "Running", "Leaping", "Flight", "Swimming", "Teleportation", "Tunneling",
]
