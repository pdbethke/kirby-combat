"""from_dict — reverse of to_dict with type dispatch."""
import pytest

from kirby_combat.serialization import to_dict, from_dict
from kirby_combat.scene import Position, Scene, SceneBounds, AmbientConditions
from kirby_combat.models import Combatant
from kirby_combat.vehicles import Vehicle


def test_round_trip_position():
    p = Position(x=1.0, y=2.0, z=3.0, facing=0.5)
    assert from_dict(to_dict(p)) == p


def test_round_trip_combatant():
    c = Combatant(
        id="a", name="a", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    restored = from_dict(to_dict(c))
    assert restored == c
    assert isinstance(restored, Combatant)


def test_round_trip_vehicle_preserves_subclass():
    v = Vehicle.make(
        id="v1", name="Car",
        size=2, body=8, def_=4, pd=4, ed=4,
        speed=3, dex=11, str_=20,
        max_stun=20, max_end=0,
        movement_inches={"ground": 12},
        passengers=[],
    )
    restored = from_dict(to_dict(v))
    assert isinstance(restored, Vehicle)
    assert restored.size == 2


def test_round_trip_combatant_tagged_with_the_new_class_name():
    """to_dict pins StatBlockCombatant's wire tag to "Combatant" so
    already-persisted sessions keep loading (see to_dict.py's
    _STABLE_WIRE_TAGS). This test pins the OTHER direction: from_dict must
    also accept "StatBlockCombatant" -- the class's real __name__ post
    rename -- so nothing written by some future code path that emits the
    new name (or a hand-built payload, or a test) is left stranded either.
    The tolerance is deliberate, not incidental -- this is what pins it."""
    d = {
        "__type__": "StatBlockCombatant",
        "id": "a", "name": "a", "ocv": 8, "dcv": 8, "omcv": 5, "dmcv": 5,
        "spd": 4, "dex": 20, "ego": 15, "str_": 15, "con": 15, "pre": 15,
        "rec": 5, "pd": 5, "ed": 5, "rpd": 0, "red": 0, "md": 5,
        "power_defense": 0, "flash_defense": 0,
        "max_stun": 30, "max_body": 15, "max_end": 30,
        "current_stun": 30, "current_body": 15, "current_end": 30,
        "attacks": [], "defenses": [], "csls": [],
        "is_mentalist": False, "is_npc": False, "knockback_resistance": 0,
    }
    restored = from_dict(d)
    assert isinstance(restored, Combatant)  # Combatant IS StatBlockCombatant
    assert restored.ocv == 8
    assert restored.current_stun == 30


def test_unknown_type_raises():
    with pytest.raises(TypeError, match="unknown type"):
        from_dict({"__type__": "NotAThing", "x": 1})


def test_round_trip_nested_scene():
    s = Scene(
        id="s1", name="E",
        bounds=SceneBounds(0, 0, 0, 10, 10, 5),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(light_level=2),
        combatant_positions={"a": Position(1.0, 2.0, 0.0)},
    )
    restored = from_dict(to_dict(s))
    assert restored.ambient.light_level == 2
    assert restored.combatant_positions["a"] == Position(1.0, 2.0, 0.0)
