"""Movement actions — base class + per-power subclasses (Running, Flight, etc.).

Movement encompasses three modes per HERO 6E2 pg 53:
  - half-move:    half your inches; full DCV, full OCV
  - full-move:    full inches; 1/2 DCV, full OCV
  - noncombat:    inches × noncombat_multiplier; 0 OCV and 0 DCV (cannot attack
                  and no defense)
"""
from kirby_combat.actions.movement.base import MovementAction

__all__ = ["MovementAction"]
