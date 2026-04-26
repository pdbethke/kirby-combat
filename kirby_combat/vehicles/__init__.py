"""Vehicles — HDC-shaped Combatant subtype."""
from kirby_combat.vehicles.vehicle import (
    Vehicle, Passenger, max_passengers_for_size,
)
from kirby_combat.vehicles.passenger import (
    passenger_cover_level, can_attack_out,
    apply_shared_fate, passenger_can_be_rescued,
    SharedFateResult,
)

__all__ = [
    "Vehicle", "Passenger", "max_passengers_for_size",
    "passenger_cover_level", "can_attack_out",
    "apply_shared_fate", "passenger_can_be_rescued",
    "SharedFateResult",
]
