"""Move-Through — velocity-based full-phase slam attack.

Per 6E2 p72 §MOVE THROUGH:
- Damage DC = STR_DC + floor(velocity_m / 6), STR_DC = floor(STR / 5)
- Attacker takes 1/2 of the STUN/BODY done to target (FULL if no Knockback —
  e.g., target is immovable or KB-resistance ≥ KB distance, OR attacker
  voluntarily chose to take full damage to do more themselves).
- Attacker: -floor(velocity_m / 10) OCV (scales with velocity), -3 DCV
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
    attacker_self_damage_dc: int              # legacy: same DC (deprecated; use fraction)
    ocv_modifier: int                         # -floor(velocity_m / 10)
    dcv_modifier: int                         # always -3
    phase_cost: Literal["half", "full"]       # "full" for Move-Through
    knockback_basis: Literal["damage", "velocity"]   # "velocity" for Move-Through
    # Per 6E2 p72: attacker takes 1/2 of STUN/BODY done normally; FULL if
    # target resisted Knockback (immovable wall, KB-resistance ≥ KB) OR
    # the attacker voluntarily chose to take full damage. Combat-session
    # layer applies this fraction to the resolved damage.
    attacker_self_damage_fraction: float = 0.5


class MoveThrough:
    """Compute Move-Through attack parameters."""

    name: str = "move_through"

    @staticmethod
    def compute(
        attacker_str: int,
        velocity_mps: float,
        target_resisted_kb: bool = False,
    ) -> MoveThroughOutcome:
        """Compute Move-Through attack DC and modifiers.

        Required:
            attacker_str           — attacker's STR.
            velocity_mps           — attacker's velocity at impact, in m/phase.
        Optional:
            target_resisted_kb     — True if the target took no Knockback
                (immovable wall, KB-resistance ≥ KB distance, or attacker
                opts to take full damage). Per 6E2 p72, this changes the
                attacker's self-damage fraction from 1/2 to 1.0.
        """
        v = max(0.0, velocity_mps)
        s = max(0, attacker_str)
        str_dc = s // 5
        velocity_dc = math.floor(v / 6.0)
        damage_dc = str_dc + velocity_dc
        ocv_penalty = -math.floor(v / 10.0)
        self_damage_fraction = 1.0 if target_resisted_kb else 0.5
        return MoveThroughOutcome(
            damage_dc=damage_dc,
            attacker_self_damage_dc=damage_dc,    # legacy, kept for back-compat
            ocv_modifier=ocv_penalty,
            dcv_modifier=-3,
            phase_cost="full",
            knockback_basis="velocity",
            attacker_self_damage_fraction=self_damage_fraction,
        )
