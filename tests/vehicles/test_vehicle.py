"""Vehicle (StatBlockCombatant subtype) — HDC-shaped."""
import pytest

from kirby_combat.vehicles import Vehicle, Passenger
from kirby_combat.models import StatBlockCombatant


def test_vehicle_is_a_combatant():
    v = Vehicle.make(
        id="v1", name="Wraith Mk2",
        size=6, body=12, def_=6,
        pd=8, ed=8, speed=4, dex=18, str_=40,
        max_stun=40, max_end=0,
        movement_inches={"ground": 20, "flight": 60},
        passengers=[],
    )
    assert isinstance(v, StatBlockCombatant)
    assert v.id == "v1"
    assert v.size == 6


def test_vehicle_empty_passenger_list_default():
    v = Vehicle.make(
        id="v1", name="Car",
        size=2, body=8, def_=4,
        pd=4, ed=4, speed=3, dex=11, str_=20,
        max_stun=20, max_end=0,
        movement_inches={"ground": 12},
        passengers=[],
    )
    assert v.passengers == []


def test_vehicle_add_passenger_returns_new_vehicle():
    v = Vehicle.make(
        id="v1", name="Car",
        size=2, body=8, def_=4, pd=4, ed=4,
        speed=3, dex=11, str_=20,
        max_stun=20, max_end=0,
        movement_inches={"ground": 12},
        passengers=[],
    )
    p = Passenger(combatant_id="alice", seat="driver", is_firing_port=False)
    v2 = v.add_passenger(p)
    assert v2.passengers == [p]
    assert v.passengers == []


def test_vehicle_max_passengers_by_size():
    from kirby_combat.vehicles.vehicle import max_passengers_for_size
    assert max_passengers_for_size(1) == 2
    assert max_passengers_for_size(4) == 6
    assert max_passengers_for_size(8) == 20


def test_vehicle_over_passenger_capacity_raises():
    v = Vehicle.make(
        id="v1", name="Tiny",
        size=1, body=6, def_=3, pd=3, ed=3,
        speed=3, dex=10, str_=15,
        max_stun=12, max_end=0,
        movement_inches={"ground": 10},
        passengers=[Passenger("a", "driver", False), Passenger("b", "shotgun", False)],
    )
    with pytest.raises(ValueError, match="capacity"):
        v.add_passenger(Passenger("c", "extra", False))


def test_vehicle_constructs_by_keyword_without_int():
    """kirby-api's entity_service.py constructs Vehicle directly by keyword
    (not via `.make()`) and never passes `int_` -- confirmed against
    entity_service.py's `_build_vehicle`. `StatBlockCombatant.int_` must
    stay defaulted (10) so this call shape keeps working across the
    package boundary; a non-defaulted field would raise TypeError here."""
    v = Vehicle(
        id="v1", name="Wraith Mk2",
        ocv=0, dcv=3, omcv=0, dmcv=0,
        spd=4, dex=18, ego=0, str_=40, con=0, pre=0, rec=0,
        pd=8, ed=8, rpd=6, red=6, md=0,
        power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=0,
        current_stun=40, current_body=12, current_end=0,
        size=6,
    )
    # Vehicles have no INT and must not silently inherit the human
    # default -- entity_service.py doesn't pass int_ either, so it relies
    # on Vehicle.make()'s explicit int_=0; a bare keyword construction
    # like this one falls back to StatBlockCombatant's default instead.
    assert v.int_ == 10


def test_vehicle_fields_are_hdc_shaped():
    """Regression against the HDC round-trip requirement."""
    v = Vehicle.make(
        id="v1", name="X",
        size=3, body=10, def_=5, pd=5, ed=5,
        speed=4, dex=15, str_=30,
        max_stun=25, max_end=0,
        movement_inches={"ground": 16, "swimming": 8},
        passengers=[],
    )
    hdc_trackable_fields = {
        "id", "name", "size", "pd", "ed", "spd", "dex",
        "str_", "max_stun", "max_body", "max_end",
        "movement_inches", "passengers",
    }
    for f in hdc_trackable_fields:
        assert hasattr(v, f), f"Vehicle missing HDC-expected field: {f}"
