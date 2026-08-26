"""from_dict — reverse of to_dict with type dispatch."""
import pytest

from kirby_combat.serialization import to_dict, from_dict
from kirby_combat.scene import Position, Scene, SceneBounds, AmbientConditions
from kirby_combat.models import StatBlockCombatant
from kirby_combat.vehicles import Vehicle


def test_round_trip_position():
    p = Position(x=1.0, y=2.0, z=3.0, facing=0.5)
    assert from_dict(to_dict(p)) == p


def test_round_trip_combatant():
    c = StatBlockCombatant(
        id="a", name="a", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    restored = from_dict(to_dict(c))
    assert restored == c
    assert isinstance(restored, StatBlockCombatant)


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


def test_from_dict_tolerates_a_payload_persisted_before_the_rename():
    """The real regression is THIS direction, not the new-name one.

    Rows already sitting in combat_session.payload_jsonb from before the
    StatBlockCombatant rename carry "__type__": "Combatant" -- written by
    the OLD to_dict, which no longer exists to produce this payload. So
    this hand-builds the tag literally, rather than routing it through
    to_dict(), which would just prove the round-trip agrees with itself
    and guard nothing: if the emit side were ever reverted back to
    type(obj).__name__, a from_dict(to_dict(...)) test would still pass
    (both sides would agree on "StatBlockCombatant") while every
    already-persisted "Combatant" row silently failed to load. Only a
    payload the production code never had a hand in building can catch
    that.
    """
    d = {
        "__type__": "Combatant",
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
    assert isinstance(restored, StatBlockCombatant)  # "Combatant" tag resolves to StatBlockCombatant
    assert restored.ocv == 8
    assert restored.current_stun == 30


def test_round_trip_combatant_tagged_with_the_new_class_name():
    """Harmless companion to the test above, not a substitute for it: this
    one resolves via the pre-existing automatic cls.__name__ registration
    and was never broken by the rename, so it guards nothing on its own."""
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
    assert isinstance(restored, StatBlockCombatant)
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
