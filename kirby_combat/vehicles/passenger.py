"""Passenger mechanics — cover from vehicle, firing ports, shared fate.

6E Vehicles supplement: passengers inherit the vehicle's cover level. Firing
ports allow attacking out (with -1 to inherited cover). Open vehicles (small
ground vehicles, motorcycles) provide no cover.
"""
from __future__ import annotations

from dataclasses import dataclass

from kirby_combat.vehicles.vehicle import Vehicle, Passenger


def passenger_cover_level(vehicle: Vehicle, passenger: Passenger) -> int:
    """Cover level a passenger inherits from a vehicle.

    Open-topped (size < 3 with only "ground" movement) -> 0.
    Otherwise base cover scales with size, capped at 4 (full).
    Firing port reduces inherited cover by 1.
    """
    is_open_topped = (
        vehicle.size < 3
        and set(vehicle.movement_inches.keys()) <= {"ground"}
    )
    if is_open_topped:
        base = 0
    else:
        # Larger vehicles -> more cover; cap at full (4).
        base = min(4, max(2, vehicle.size // 2 + 1))

    if passenger.is_firing_port:
        return max(0, base - 1)
    return base


def can_attack_out(vehicle: Vehicle, passenger: Passenger) -> bool:
    """A passenger can attack out only via a firing port (or from open-top)."""
    is_open_topped = (
        vehicle.size < 3
        and set(vehicle.movement_inches.keys()) <= {"ground"}
    )
    if is_open_topped:
        return True
    return passenger.is_firing_port


@dataclass
class SharedFateResult:
    vehicle_id: str
    passengers_affected: list[str]
    body_dealt_per_passenger: int
    audit: list[str]


def apply_shared_fate(vehicle: Vehicle, vehicle_destroyed: bool) -> SharedFateResult:
    """When a vehicle is destroyed/crashed, passengers take damage from the wreck.

    Per 6E Vehicles: when a vehicle is destroyed at speed, passengers take
    damage equal to half the vehicle's BODY (rounded down) as Normal Damage.
    A crash without destruction (e.g., losing control) inflicts ramming damage
    as a separate computation.
    """
    audit: list[str] = []
    if not vehicle_destroyed:
        return SharedFateResult(
            vehicle_id=vehicle.id, passengers_affected=[],
            body_dealt_per_passenger=0,
            audit=["Vehicle not destroyed; no shared-fate damage"],
        )
    body_per = vehicle.max_body // 2
    affected = [p.combatant_id for p in vehicle.passengers]
    audit.append(
        f"Vehicle {vehicle.id} destroyed; {len(affected)} passengers take "
        f"{body_per} BODY each (half vehicle BODY)"
    )
    return SharedFateResult(
        vehicle_id=vehicle.id, passengers_affected=affected,
        body_dealt_per_passenger=body_per, audit=audit,
    )


def passenger_can_be_rescued(vehicle: Vehicle, passenger: Passenger) -> bool:
    """Passengers can be rescued from a non-destroyed crashed vehicle."""
    return vehicle.current_body > 0
