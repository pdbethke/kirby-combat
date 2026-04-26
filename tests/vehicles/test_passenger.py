"""Passenger mechanics — cover, firing ports, shared fate."""
import pytest

from kirby_combat.vehicles import Vehicle, Passenger
from kirby_combat.vehicles.passenger import (
    passenger_cover_level, can_attack_out,
    apply_shared_fate, passenger_can_be_rescued,
)


def _enclosed_van(size=4) -> Vehicle:
    return Vehicle.make(
        id="van", name="Van",
        size=size, body=10, def_=5, pd=5, ed=5,
        speed=3, dex=11, str_=25,
        max_stun=20, max_end=0,
        movement_inches={"ground": 14},
        passengers=[],
    )


def _open_motorcycle() -> Vehicle:
    return Vehicle.make(
        id="bike", name="Bike",
        size=1, body=4, def_=2, pd=2, ed=2,
        speed=4, dex=14, str_=15,
        max_stun=10, max_end=0,
        movement_inches={"ground": 30},
        passengers=[],
    )


def test_passenger_gets_vehicle_cover_level_from_size():
    v = _enclosed_van(size=4)   # base cover -> min(4, 4//2+1) = 3
    p = Passenger("alice", "driver", False)
    assert passenger_cover_level(v, p) == 3


def test_firing_port_passenger_can_attack_through_vehicle():
    v = _enclosed_van()
    p = Passenger("alice", "gunner", is_firing_port=True)
    assert can_attack_out(v, p) is True


def test_non_firing_port_passenger_cannot_attack_outside():
    v = _enclosed_van()
    p = Passenger("alice", "shotgun", is_firing_port=False)
    assert can_attack_out(v, p) is False


def test_passenger_body_damage_when_vehicle_destroyed():
    v = _enclosed_van()
    v = v.add_passenger(Passenger("alice", "driver", False))
    v = v.add_passenger(Passenger("bob", "shotgun", False))
    r = apply_shared_fate(v, vehicle_destroyed=True)
    assert r.passengers_affected == ["alice", "bob"]
    assert r.body_dealt_per_passenger == 5    # half of vehicle BODY 10


def test_passenger_rescue_on_vehicle_crash():
    v = _enclosed_van()
    p = Passenger("alice", "driver", False)
    v = v.add_passenger(p)
    # Vehicle still has BODY (not destroyed) — can rescue
    assert passenger_can_be_rescued(v, p) is True


def test_open_motorcycle_provides_no_cover_and_can_attack_out():
    v = _open_motorcycle()
    p = Passenger("alice", "driver", False)
    assert passenger_cover_level(v, p) == 0
    assert can_attack_out(v, p) is True
