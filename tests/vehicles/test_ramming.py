"""Ramming — extreme move-through."""
import pytest

from kirby_combat.vehicles import Vehicle
from kirby_combat.vehicles.ramming import resolve_ramming, ramming_dc


def _car(size=3) -> Vehicle:
    return Vehicle.make(
        id="car", name="Car",
        size=size, body=10, def_=4, pd=4, ed=4,
        speed=4, dex=12, str_=20,
        max_stun=20, max_end=0,
        movement_inches={"ground": 30},
        passengers=[],
    )


def test_ramming_dc_scales_with_vehicle_mass_and_velocity():
    car = _car(size=3)
    # Size 3 * 24 m/seg / 12 = 6 base DC
    base, extra = ramming_dc(car, velocity_m_per_segment=24)
    assert base == 6
    assert extra == 0
    # Bigger vehicle, same velocity -> more DC
    truck = _car(size=6)
    base2, _ = ramming_dc(truck, 24)
    assert base2 > base


def test_ramming_attacker_takes_half_damage_like_move_through():
    car = _car(size=3)
    r = resolve_ramming(car, target_id="t", velocity_m_per_segment=24)
    assert r.attacker_damage_dice == r.total_dc // 2


def test_ramming_vehicle_body_decremented_on_successful_ram():
    car = _car()
    r = resolve_ramming(car, target_id="t", velocity_m_per_segment=24)
    assert r.vehicle_body_decremented == 1


def test_ramming_into_structure_uses_structure_damage_cascade():
    car = _car()
    r = resolve_ramming(car, target_id="wall_a", velocity_m_per_segment=24,
                        target_is_structure=True)
    # The audit trail should note structure cascade
    assert any("structure" in line.lower() for line in r.audit)


def test_ramming_at_over_60_velocity_adds_extra_dc():
    car = _car(size=3)
    base_lo, extra_lo = ramming_dc(car, 60.0)
    base_hi, extra_hi = ramming_dc(car, 61.0)
    assert extra_lo == 0
    assert extra_hi == 1
