"""AoE blasts catch destructible constructs in-template (spec §1.3)."""
from kirby_combat.scene import Construct, Position
from kirby_combat.actions.area_of_effect import AreaOfEffect


def _wall_construct(obj_id, x, y):
    return Construct(obj_id=obj_id, kind="wall",
                     segment=(Position(x - 0.5, y, 0), Position(x + 0.5, y, 0)),
                     def_value=2, body=4)


def test_radius_catches_construct_in_blast():
    out = AreaOfEffect.compute_radius(
        base_dc=6, epicenter=(0.0, 0.0), radius_m=5.0,
        combatant_positions={},
        constructs=[_wall_construct("near", 2.0, 0.0), _wall_construct("far", 20.0, 0.0)],
    )
    assert out.affected_constructs == ["near"]


def test_no_constructs_arg_is_empty_not_none():
    out = AreaOfEffect.compute_radius(
        base_dc=6, epicenter=(0.0, 0.0), radius_m=5.0, combatant_positions={})
    assert out.affected_constructs == []


def test_indestructible_construct_not_caught():
    """A construct without def_value/body is not destructible — must be excluded."""
    indestructible = Construct(obj_id="steel_wall", kind="wall",
                               segment=(Position(-0.5, 0, 0), Position(0.5, 0, 0)))
    out = AreaOfEffect.compute_radius(
        base_dc=6, epicenter=(0.0, 0.0), radius_m=5.0,
        combatant_positions={},
        constructs=[indestructible],
    )
    assert out.affected_constructs == []


def test_cone_catches_construct_in_template():
    import math
    # Cone pointing along +x axis; wall at (3, 0) is directly ahead
    out = AreaOfEffect.compute_cone(
        base_dc=6, origin=(0.0, 0.0), direction_rad=0.0,
        half_angle_rad=math.pi / 6, length_m=5.0,
        combatant_positions={},
        constructs=[_wall_construct("ahead", 3.0, 0.0), _wall_construct("behind", -3.0, 0.0)],
    )
    assert "ahead" in out.affected_constructs
    assert "behind" not in out.affected_constructs


def test_line_catches_construct_in_template():
    # Line from (0,0) to (10,0), width 2m — construct at (5, 0.5) is within 1m
    out = AreaOfEffect.compute_line(
        base_dc=6, start=(0.0, 0.0), end=(10.0, 0.0), width_m=2.0,
        combatant_positions={},
        constructs=[_wall_construct("inline", 5.0, 0.5), _wall_construct("wide", 5.0, 5.0)],
    )
    assert "inline" in out.affected_constructs
    assert "wide" not in out.affected_constructs
