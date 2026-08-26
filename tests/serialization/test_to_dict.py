"""to_dict — convert engine objects to JSON-safe dicts."""
import pytest

from kirby_combat.serialization import to_dict
from kirby_combat.scene import Scene, SceneBounds, Position, AmbientConditions
from kirby_combat.models import StatBlockCombatant
from kirby_combat.vehicles import Vehicle


def test_position_to_dict_round_trippable_primitives_only():
    p = Position(x=1.0, y=2.0, z=3.0, facing=0.5)
    d = to_dict(p)
    # Position has __type__ tag but values are primitives
    assert d["x"] == 1.0
    assert d["y"] == 2.0
    assert d["z"] == 3.0
    assert d["facing"] == 0.5
    for k, v in d.items():
        assert isinstance(v, (int, float, str, bool, type(None)))


def test_scene_to_dict_includes_type_tag():
    s = Scene(
        id="s1", name="Empty",
        bounds=SceneBounds(0, 0, 0, 10, 10, 5),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    d = to_dict(s)
    assert d["__type__"] == "Scene"
    assert d["id"] == "s1"


def test_combatant_to_dict_has_all_fields():
    # NOT synthetic: this asserts the stable wire tag `"Combatant"` that
    # to_dict pins for StatBlockCombatant specifically (see
    # kirby_combat/serialization/to_dict.py _STABLE_WIRE_TAGS).
    c = StatBlockCombatant(
        id="a", name="a", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, int_=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    d = to_dict(c)
    assert d["__type__"] == "Combatant"
    assert d["ocv"] == 8
    assert "attacks" in d


def test_vehicle_to_dict_discriminator():
    v = Vehicle.make(
        id="v1", name="Car",
        size=2, body=8, def_=4, pd=4, ed=4,
        speed=3, dex=11, str_=20,
        max_stun=20, max_end=0,
        movement_inches={"ground": 12},
        passengers=[],
    )
    d = to_dict(v)
    assert d["__type__"] == "Vehicle"
    assert d["size"] == 2


def test_to_dict_handles_nested_structures():
    s = Scene(
        id="s1", name="E",
        bounds=SceneBounds(0, 0, 0, 10, 10, 5),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={"a": Position(1.0, 2.0, 0.0)},
    )
    d = to_dict(s)
    assert d["combatant_positions"]["a"]["x"] == 1.0
