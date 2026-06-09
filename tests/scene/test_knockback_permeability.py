"""Knockback honors construct permeability (spec §1.6): porous = enter,
impermeable = collide like a wall."""
from kirby_combat.scene import (
    Scene, SceneBounds, Surface, Construct, Position, AmbientConditions,
)
from kirby_combat.models import DiceValues
from kirby_combat.template import CombatTemplate
from kirby_combat.actions.movement.knockback_movement import resolve_knockback_movement


def _ground():
    return Surface(id="g", name="ground", polygon_xy=[(-50, -50), (50, -50), (50, 50), (-50, 50)],
                   elevation_m=0.0, surface_type="ground", cover_level=0, is_supporting=True)


def _scene(constructs):
    s = Scene(id="s", name="n",
              bounds=SceneBounds(min_x=-50, min_y=-50, min_z=0, max_x=50, max_y=50, max_z=10),
              surfaces=[_ground()], walls=[], hazards=[], ambient=AmbientConditions())
    s.constructs = constructs
    return s


def _impermeable_barrier(x):
    return Construct(obj_id="bar", kind="force_wall",
                     segment=(Position(x, -5, 0), Position(x, 5, 0)), height_m=3.0,
                     blocks_los=True, blocks_movement=True, permeability="impermeable",
                     def_value=5, body=4)


def test_knockback_collides_with_impermeable_construct():
    s = _scene([_impermeable_barrier(4.0)])
    res = resolve_knockback_movement(
        combatant_id="t", attacker_pos=Position(-2, 0, 0), target_pos=Position(0, 0, 0),
        body_dealt=30, kb_resistance=0, dice=DiceValues(knockback=[1, 1]),
        scene=s, template=CombatTemplate(name="t"))
    assert res.wall_collision is not None and res.wall_collision.wall_id == "bar"
