"""Knockback movement — Phase 1 KB integrated with Scene walls/edges/hazards."""
import pytest

from kirby_combat.actions.movement.knockback_movement import (
    resolve_knockback_movement,
    KnockbackMovementResult,
    WallCollision,
)
from kirby_combat.models import DiceValues
from kirby_combat.scene import (
    Scene, SceneBounds, Surface, Wall, Hazard, HazardEffect, Position,
    AmbientConditions,
)
from kirby_combat.template import RAW_SUPERHEROIC


def _open_scene_with_ground() -> Scene:
    return Scene(
        id="s1", name="Open ground",
        bounds=SceneBounds(0, 0, 0, 100, 100, 20),
        surfaces=[Surface(id="ground", name="Ground",
                          polygon_xy=[(0, 0), (100, 0), (100, 100), (0, 100)],
                          elevation_m=0.0, surface_type="ground",
                          cover_level=0, is_supporting=True)],
        walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )


def test_no_kb_when_body_resisted():
    s = _open_scene_with_ground()
    out = resolve_knockback_movement(
        combatant_id="alice",
        attacker_pos=Position(0, 0, 0),
        target_pos=Position(10, 0, 0),
        body_dealt=2, kb_resistance=10,    # resisted (effective ≤ 0)
        dice=DiceValues(knockback=[3, 3, 3]),
        scene=s, template=RAW_SUPERHEROIC,
    )
    assert out.intended_distance_m == 0.0
    assert out.actual_distance_traveled_m == 0.0
    assert out.final_position == Position(10, 0, 0)
    assert out.wall_collision is None
    assert out.fall is None
    assert out.hazard_triggers == []


def test_kb_in_open_field_moves_target_full_distance():
    s = _open_scene_with_ground()
    out = resolve_knockback_movement(
        combatant_id="alice",
        attacker_pos=Position(0, 5, 0),
        target_pos=Position(10, 5, 0),
        body_dealt=6, kb_resistance=0,
        dice=DiceValues(knockback=[4, 5, 4]),    # at least 3 dice — Phase 1 may sum some
        scene=s, template=RAW_SUPERHEROIC,
    )
    assert out.intended_distance_m > 0
    assert out.wall_collision is None
    assert out.fall is None
    # Direction east (+x): final_pos.x > target_pos.x
    assert out.final_position.x > 10
    assert out.actual_distance_traveled_m == out.intended_distance_m


def test_kb_into_wall_stops_at_wall():
    wall = Wall(
        id="brick", name="Brick wall",
        segment=(Position(15, 0, 0), Position(15, 10, 0)),
        height_m=3.0, blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )
    s = Scene(
        id="s1", name="With wall",
        bounds=SceneBounds(0, 0, 0, 30, 30, 10),
        surfaces=[Surface(id="g", name="g", polygon_xy=[(0, 0), (30, 0), (30, 30), (0, 30)],
                          elevation_m=0.0, surface_type="ground", cover_level=0, is_supporting=True)],
        walls=[wall], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    out = resolve_knockback_movement(
        combatant_id="alice",
        attacker_pos=Position(0, 5, 0),
        target_pos=Position(10, 5, 0),
        body_dealt=10, kb_resistance=0,
        dice=DiceValues(knockback=[6, 6, 6, 6, 6]),    # very large KB
        scene=s, template=RAW_SUPERHEROIC,
    )
    assert out.wall_collision is not None
    assert out.wall_collision.wall_id == "brick"
    # Target stops at x=15 (wall position)
    assert out.final_position.x == pytest.approx(15.0, abs=1e-6)
    assert out.actual_distance_traveled_m < out.intended_distance_m
    assert out.actual_distance_traveled_m == pytest.approx(5.0, abs=1e-6)


def test_kb_off_rooftop_triggers_fall():
    rooftop = Surface(
        id="roof", name="Roof",
        polygon_xy=[(5, 5), (15, 5), (15, 15), (5, 15)],
        elevation_m=12.0, surface_type="rooftop",
        cover_level=0, is_supporting=True,
    )
    ground = Surface(
        id="ground", name="Ground",
        polygon_xy=[(0, 0), (30, 0), (30, 30), (0, 30)],
        elevation_m=0.0, surface_type="ground",
        cover_level=0, is_supporting=True,
    )
    s = Scene(
        id="s1", name="Building",
        bounds=SceneBounds(0, 0, 0, 30, 30, 20),
        surfaces=[rooftop, ground], walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    out = resolve_knockback_movement(
        combatant_id="alice",
        attacker_pos=Position(20, 10, 12),     # to the east, on (or past) rooftop
        target_pos=Position(8, 10, 12),         # near the west edge
        body_dealt=6, kb_resistance=0,
        dice=DiceValues(knockback=[3, 4, 3]),  # KB direction: -x (away from attacker)
        scene=s, template=RAW_SUPERHEROIC,
    )
    # KB pushes target west past x=5 → off rooftop → falls
    assert out.fall is not None
    assert out.fall.landed_at.z == 0.0
    assert out.final_position.z == 0.0


def test_kb_through_hazard_triggers_it():
    fire = Hazard(
        id="fire", name="Fire",
        polygon_xy=[(8, 0), (12, 0), (12, 10), (8, 10)],
        elevation_range_m=(0.0, 5.0),
        trigger="on_pass",
        effect=HazardEffect(damage_dice=2, damage_type="energy"),
    )
    s = Scene(
        id="s1", name="With fire",
        bounds=SceneBounds(0, 0, 0, 30, 30, 10),
        surfaces=[Surface("g", "g", [(0, 0), (30, 0), (30, 30), (0, 30)],
                          0.0, "ground", 0, True)],
        walls=[], hazards=[fire],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    out = resolve_knockback_movement(
        combatant_id="alice",
        attacker_pos=Position(0, 5, 0),
        target_pos=Position(5, 5, 0),
        body_dealt=8, kb_resistance=0,
        dice=DiceValues(knockback=[6, 6, 6, 6]),    # big KB pushes through fire
        scene=s, template=RAW_SUPERHEROIC,
    )
    # KB path goes from (5,5) eastward, crossing fire polygon (x ∈ [8, 12])
    assert len(out.hazard_triggers) >= 1
    assert out.hazard_triggers[0].hazard_id == "fire"


def test_collision_damage_dice_exposed_for_caller():
    s = _open_scene_with_ground()
    out = resolve_knockback_movement(
        combatant_id="alice",
        attacker_pos=Position(0, 0, 0),
        target_pos=Position(10, 0, 0),
        body_dealt=6, kb_resistance=0,
        dice=DiceValues(knockback=[4, 5, 4]),
        scene=s, template=RAW_SUPERHEROIC,
    )
    # Phase 1's KnockbackResult.damage_dice — caller applies on wall hit
    assert isinstance(out.collision_damage_dice, int)
    assert out.collision_damage_dice >= 0


def test_direction_uses_attacker_to_target_vector():
    s = _open_scene_with_ground()
    # Attacker NW, target SE → KB direction is SE
    out = resolve_knockback_movement(
        combatant_id="alice",
        attacker_pos=Position(0, 10, 0),
        target_pos=Position(10, 0, 0),
        body_dealt=4, kb_resistance=0,
        dice=DiceValues(knockback=[3, 3]),
        scene=s, template=RAW_SUPERHEROIC,
    )
    # direction_xy is normalized; (10-0, 0-10) = (10, -10) normalized = (~0.707, -0.707)
    assert out.direction_xy[0] == pytest.approx(0.7071, abs=0.01)
    assert out.direction_xy[1] == pytest.approx(-0.7071, abs=0.01)


def test_attacker_and_target_same_position_uses_default_direction():
    s = _open_scene_with_ground()
    out = resolve_knockback_movement(
        combatant_id="alice",
        attacker_pos=Position(5, 5, 0),
        target_pos=Position(5, 5, 0),
        body_dealt=4, kb_resistance=0,
        dice=DiceValues(knockback=[3, 3]),
        scene=s, template=RAW_SUPERHEROIC,
    )
    assert out.direction_xy == (1.0, 0.0)    # default east
