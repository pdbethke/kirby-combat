"""Unified Construct model (spec 2026-06-09 §1.1)."""
from kirby_combat.scene import (
    Scene, SceneBounds, Wall, Hazard, HazardEffect, Position, AmbientConditions,
    Construct, ConstructEffect, construct_from_wall, construct_from_hazard,
)


def _wall(**kw):
    base = dict(id="w1", name="wall", segment=(Position(0, 0, 0), Position(0, 10, 0)),
                height_m=2.0, blocks_los=True, blocks_movement=True, cover_level=4, body=8)
    base.update(kw)
    return Wall(**base)


def test_construct_destructible_flag():
    c = Construct(obj_id="x", kind="wall", def_value=5, body=8)
    assert c.destructible is True
    assert Construct(obj_id="y", kind="hazard_zone").destructible is False


def test_construct_from_wall_carries_geometry_and_durability():
    w = _wall(def_value=6)
    c = construct_from_wall(w)
    assert c.obj_id == "w1" and c.kind == "wall"
    assert c.segment == w.segment and c.height_m == 2.0
    assert c.blocks_los and c.blocks_movement
    assert c.permeability == "impermeable"  # blocks_movement -> impermeable
    assert c.cover_level == 4
    assert c.def_value == 6 and c.body == 8 and c.destructible


def test_construct_from_hazard_carries_effect():
    hz = Hazard(id="h1", name="fire", polygon_xy=[(0, 0), (4, 0), (4, 4), (0, 4)],
                elevation_range_m=(0.0, 3.0), trigger="every_segment",
                effect=HazardEffect(damage_dice=2, damage_type="normal"))
    c = construct_from_hazard(hz)
    assert c.obj_id == "h1" and c.kind == "hazard_zone"
    assert c.polygon_xy == hz.polygon_xy and c.permeability == "porous"
    assert c.effect.kind == "damage" and c.effect.trigger == "every_segment"
    assert c.effect.damage_dice == 2 and not c.destructible


def test_scene_constructs_defaults_empty():
    s = Scene(id="s", name="n",
              bounds=SceneBounds(min_x=0, min_y=0, min_z=0, max_x=10, max_y=10, max_z=5),
              surfaces=[], walls=[], hazards=[], ambient=AmbientConditions())
    assert s.constructs == []


def test_construct_from_hazard_rejects_empty_effect():
    import pytest
    hz = Hazard(id="h0", name="nothing", polygon_xy=[(0, 0), (1, 0), (1, 1)],
                elevation_range_m=(0.0, 1.0), trigger="on_enter",
                effect=HazardEffect(damage_dice=0, damage_type="normal", status_inflicted=None))
    with pytest.raises(ValueError):
        construct_from_hazard(hz)


def test_constructs_containing_point():
    from kirby_combat.scene import Construct, Position
    from kirby_combat.scene.construct import constructs_containing
    pool = Construct(obj_id="pool", kind="hazard_zone",
                     polygon_xy=[(0, 0), (4, 0), (4, 4), (0, 4)], elevation_range_m=(-2.0, 0.0))
    inside = constructs_containing(Position(2, 2, -1), [pool])
    outside = constructs_containing(Position(9, 9, -1), [pool])
    above = constructs_containing(Position(2, 2, 5), [pool])  # out of elevation range
    assert [c.obj_id for c in inside] == ["pool"]
    assert outside == [] and above == []


def test_construct_from_spawn_spec_builds_force_wall():
    from kirby_combat.scene.construct import construct_from_spawn_spec
    from kirby_combat.scene import Position
    c = construct_from_spawn_spec(
        obj_id="fw1", kind="force_wall",
        segment=(Position(0, 0, 0), Position(0, 4, 0)), height_m=3.0,
        def_value=5, body=4, source_combatant_id="cheshire", created_at_seq=12)
    assert c.kind == "force_wall" and c.blocks_los and c.blocks_movement
    assert c.permeability == "impermeable" and c.def_value == 5 and c.body == 4
    assert c.source_combatant_id == "cheshire" and c.destructible
