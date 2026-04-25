"""Move-Through — velocity-based full-phase slam attack.

HERO 6E2 pg 71:
- Damage DC = STR_DC + floor(velocity_m / 6), STR_DC = floor(STR / 5)
- Attacker takes the same DC of damage (defended by attacker's rPD/rED — caller applies)
- Attacker: -floor(velocity_m / 5) OCV (scales with velocity), -3 DCV
- Full-phase action
- Knockback uses velocity-based rules (not damage-based) — flagged for caller
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


@dataclass
class MoveThroughOutcome:
    damage_dc: int                            # damage DC inflicted on target
    attacker_self_damage_dc: int              # damage attacker takes (same DC)
    ocv_modifier: int                         # -floor(velocity_m / 5)
    dcv_modifier: int                         # always -3
    phase_cost: Literal["half", "full"]       # "full" for Move-Through
    knockback_basis: Literal["damage", "velocity"]   # "velocity" for Move-Through


class MoveThrough:
    """Compute Move-Through attack parameters."""

    name: str = "move_through"

    @staticmethod
    def compute(
        attacker_str: int,
        velocity_mps: float,
    ) -> MoveThroughOutcome:
        """Compute Move-Through attack DC and modifiers.

        Required:
            attacker_str   — attacker's STR.
            velocity_mps   — attacker's velocity at impact, in m/phase.
        """
        v = max(0.0, velocity_mps)
        s = max(0, attacker_str)
        str_dc = s // 5
        velocity_dc = math.floor(v / 6.0)
        damage_dc = str_dc + velocity_dc
        ocv_penalty = -math.floor(v / 5.0)
        return MoveThroughOutcome(
            damage_dc=damage_dc,
            attacker_self_damage_dc=damage_dc,
            ocv_modifier=ocv_penalty,
            dcv_modifier=-3,
            phase_cost="full",
            knockback_basis="velocity",
        )
