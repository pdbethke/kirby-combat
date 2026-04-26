"""Ramming — vehicle move-through writ large.

Per 6E Vehicles supplement pg 33: vehicle ramming inflicts damage scaled by
vehicle SIZE and velocity. Attacker takes half damage like a Move Through.
At extreme velocity (>60 m/segment) an extra DC is added.

DC formula: DC = round((SIZE * velocity_m_per_segment) / 12)
At v > 60 m/segment, DC += 1.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.vehicles.vehicle import Vehicle


@dataclass
class RammingResult:
    vehicle_id: str
    target_id: str
    velocity_m_per_segment: float
    base_dc: int
    extra_dc_high_velocity: int
    total_dc: int
    target_damage_dice: int
    attacker_damage_dice: int            # half DC, attacker self-damage
    vehicle_body_decremented: int        # how much vehicle BODY took
    audit: list[str] = field(default_factory=list)


def ramming_dc(vehicle: Vehicle, velocity_m_per_segment: float) -> tuple[int, int]:
    """Return (base_dc, extra_dc) for a ramming attack.

    base_dc = round(SIZE * v / 12). extra_dc = +1 if v > 60.
    """
    base = round((vehicle.size * velocity_m_per_segment) / 12)
    extra = 1 if velocity_m_per_segment > 60 else 0
    return base, extra


def resolve_ramming(
    vehicle: Vehicle,
    target_id: str,
    velocity_m_per_segment: float,
    target_is_structure: bool = False,
) -> RammingResult:
    base_dc, extra_dc = ramming_dc(vehicle, velocity_m_per_segment)
    total_dc = base_dc + extra_dc

    # Target takes total_dc d6 normal damage; attacker takes half (round down)
    target_dice = total_dc
    attacker_dice = total_dc // 2
    # Vehicle BODY decrements by 1 per ram per 6E Vehicles supplement
    vehicle_body_dec = 1

    audit = [
        f"Ramming: SIZE={vehicle.size}, v={velocity_m_per_segment} m/seg -> "
        f"base DC={base_dc}, extra={extra_dc}, total={total_dc}",
        f"Target takes {target_dice}d6; attacker self-damage {attacker_dice}d6",
    ]
    if target_is_structure:
        audit.append("Target is a structure: damage feeds structure cascade")

    return RammingResult(
        vehicle_id=vehicle.id, target_id=target_id,
        velocity_m_per_segment=velocity_m_per_segment,
        base_dc=base_dc, extra_dc_high_velocity=extra_dc,
        total_dc=total_dc, target_damage_dice=target_dice,
        attacker_damage_dice=attacker_dice,
        vehicle_body_decremented=vehicle_body_dec,
        audit=audit,
    )
