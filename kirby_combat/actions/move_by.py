"""Move-By — velocity-based half-phase attack while moving past target.

Per 6E2 p72 §MOVE BY:
    Damage = (STR/2) + (vel/10)d6
        - STR is HALVED before conversion to DCs (so str_dc = (STR // 2) // 5).
        - Each 10m of velocity contributes 1d6 → 1 DC.
    Attacker: -2 OCV, -2 DCV
    Half-phase action; attacker continues moving past target.
    Attacker takes 1/3 of the STUN/BODY done to the target as self-damage
    (see attacker_self_damage_fraction; computation of the actual damage
    happens at the combat-session layer where target defenses are known).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


@dataclass
class MoveByOutcome:
    damage_dc: int
    ocv_modifier: int                         # always -2 for Move-By
    dcv_modifier: int                         # always -2 for Move-By
    phase_cost: Literal["half", "full"]       # "half" for Move-By
    distance_past_target_m: float = 0.0       # 0 unless caller supplies movement context
    # Per 6E2 p72: attacker takes 1/3 of STUN/BODY done to the target.
    # The actual self-damage is computed by the combat-session layer once
    # target defenses are applied; this field exposes the RAW fraction.
    attacker_self_damage_fraction: float = 1.0 / 3.0


class MoveBy:
    """Compute Move-By attack parameters."""

    name: str = "move_by"

    @staticmethod
    def compute(
        attacker_str: int,
        velocity_mps: float,
        total_movement_m: float | None = None,
        distance_to_target_m: float | None = None,
    ) -> MoveByOutcome:
        """Compute Move-By attack DC and modifiers.

        Required:
            attacker_str   — attacker's STR (used to compute STR_DC = STR/5).
            velocity_mps   — attacker's velocity at impact, in meters per phase.

        Optional context for distance_past_target_m:
            total_movement_m       — total distance moved this phase
            distance_to_target_m   — distance from start to impact

        Returns MoveByOutcome with damage_dc, modifiers, phase_cost, and (if
        movement context provided) distance_past_target_m.
        """
        v = max(0.0, velocity_mps)
        s = max(0, attacker_str)
        # Per 6E2 p72: damage is (STR/2) + (vel/10)d6. STR is HALVED before DCs.
        str_dc = (s // 2) // 5
        velocity_dc = math.floor(v / 10.0)
        damage_dc = str_dc + velocity_dc

        distance_past = 0.0
        if total_movement_m is not None and distance_to_target_m is not None:
            distance_past = max(0.0, total_movement_m - distance_to_target_m)

        return MoveByOutcome(
            damage_dc=damage_dc,
            ocv_modifier=-2,
            dcv_modifier=-2,
            phase_cost="half",
            distance_past_target_m=distance_past,
            attacker_self_damage_fraction=1.0 / 3.0,
        )
