"""AoE + Scene integration + knockback geometry pass.

Per Plan 1 Task 29. Wires the basic AoE shape math (Task 14) and knockback
movement (Task 20) to actual scene walls / hazards / surfaces.
"""
from __future__ import annotations

import math

from kirby_combat.actions.area_of_effect import AreaOfEffect
from kirby_combat.actions.movement.knockback_movement import (
    resolve_knockback_movement,
)
from kirby_combat.models import DiceValues
from kirby_combat.scene import (
    AmbientConditions, Hazard, HazardEffect, Position, Scene, SceneBounds,
    Surface, Wall,
)
from kirby_combat.template import RAW_SUPERHEROIC


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ground_only_scene(combatants: dict[str, Position] | None = None) -> Scene:
    return Scene(
        id="s1", name="Test",
        bounds=SceneBounds(0, 0, 0, 50, 50, 20),
        surfaces=[
            Surface(id="ground", name="Ground",
                    polygon_xy=[(0, 0), (50, 0), (50, 50), (0, 50)],
                    elevation_m=0.0, surface_type="ground",
                    cover_level=0, is_supporting=True),
        ],
        walls=[],
        hazards=[],
        ambient=AmbientConditions(),
        combatant_positions=dict(combatants or {}),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_aoe_radius_excludes_targets_behind_wall_without_indirect():
    """Per 6E1 p339: a wall blocks LoS for AoE attack unless Indirect is bought."""
    wall = Wall(
        id="w", name="Brick",
        segment=(Position(10, 0, 0), Position(10, 20, 0)),
        height_m=5.0, blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )
    scene = Scene(
        id="s1", name="Test",
        bounds=SceneBounds(0, 0, 0, 50, 50, 20),
        surfaces=[],
        walls=[wall],
        hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={
            "alice": Position(5, 5, 1.5),       # epicenter side
            "bob":   Position(15, 5, 1.5),      # other side of wall
        },
    )
    positions = {
        "alice": (5, 5),
        "bob":   (15, 5),
    }

    # Without scene, both are in the radius
    out_no_scene = AreaOfEffect.compute_radius(
        base_dc=10, epicenter=(5, 5), radius_m=15,
        combatant_positions=positions,
    )
    assert set(out_no_scene.affected_targets) == {"alice", "bob"}

    # With scene + no indirect, bob is excluded (wall blocks LoS)
    out_scene = AreaOfEffect.compute_radius(
        base_dc=10, epicenter=(5, 5), radius_m=15,
        combatant_positions=positions,
        scene=scene, indirect=False,
    )
    assert "alice" in out_scene.affected_targets
    assert "bob" not in out_scene.affected_targets

    # With Indirect, bob is back
    out_indirect = AreaOfEffect.compute_radius(
        base_dc=10, epicenter=(5, 5), radius_m=15,
        combatant_positions=positions,
        scene=scene, indirect=True,
    )
    assert set(out_indirect.affected_targets) == {"alice", "bob"}


def test_aoe_cone_angle_derived_from_attacker_facing():
    """Cone direction can come from the attacker's facing rather than an explicit angle."""
    positions = {
        "north": (0, 10),       # 90° from +x
        "east":  (10, 0),       # 0° from +x
    }
    # Facing north (+pi/2), only the "north" combatant should be hit
    out = AreaOfEffect.compute_cone(
        base_dc=10, origin=(0, 0),
        direction_rad=0.0,                # ignored when attacker_facing given
        half_angle_rad=math.pi / 8,       # 22.5° → 45° total cone
        length_m=20,
        combatant_positions=positions,
        attacker_facing_rad=math.pi / 2,  # facing north
    )
    assert "north" in out.affected_targets
    assert "east" not in out.affected_targets


def test_aoe_line_projects_through_hazards_triggering_them():
    """A line AoE between (start, end) crosses hazards along the way and triggers them."""
    fire_zone = Hazard(
        id="fire", name="Lava",
        polygon_xy=[(8, -5), (12, -5), (12, 15), (8, 15)],   # 4m wide
        elevation_range_m=(0.0, 5.0),
        trigger="on_pass",
        effect=HazardEffect(damage_dice=4, damage_type="energy"),
    )
    scene = Scene(
        id="s1", name="Test",
        bounds=SceneBounds(0, 0, 0, 50, 50, 20),
        surfaces=[],
        walls=[],
        hazards=[fire_zone],
        ambient=AmbientConditions(),
        combatant_positions={},
    )

    out = AreaOfEffect.compute_line(
        base_dc=10,
        start=(0, 5),
        end=(20, 5),
        width_m=2,
        combatant_positions={},
        scene=scene,
        elevation_z=1.5,
    )
    # The line crosses the fire hazard polygon in xy
    assert any(t.hazard_id == "fire" for t in out.hazard_triggers)


def test_knockback_on_rooftop_triggers_falling_when_push_crosses_edge():
    """Per Task 18 + 20: a target knocked off a rooftop falls to the ground."""
    rooftop = Surface(
        id="roof", name="Roof",
        polygon_xy=[(5, 5), (15, 5), (15, 15), (5, 15)],
        elevation_m=12.0, surface_type="rooftop",
        cover_level=0, is_supporting=True,
    )
    ground = Surface(
        id="ground", name="Ground",
        polygon_xy=[(0, 0), (50, 0), (50, 50), (0, 50)],
        elevation_m=0.0, surface_type="ground",
        cover_level=0, is_supporting=True,
    )
    scene = Scene(
        id="s1", name="Tower",
        bounds=SceneBounds(0, 0, 0, 50, 50, 30),
        surfaces=[ground, rooftop],
        walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )

    # Attacker at one edge of the rooftop; target on the rooftop further in
    attacker_pos = Position(8, 10, 12.0)
    target_pos = Position(12, 10, 12.0)

    # Set up a force enough KB roll: body_dealt high, kb_resistance 0.
    # Per 6E2 p116: KB distance = (BODY - 2d6) * 2m.  With BODY=12 and a 2d6
    # roll of (1, 1) = 2, that's 10*2 = 20m of KB → off the roof.
    dice = DiceValues(knockback=[1, 1])
    res = resolve_knockback_movement(
        combatant_id="bob",
        attacker_pos=attacker_pos,
        target_pos=target_pos,
        body_dealt=12,
        kb_resistance=0,
        dice=dice,
        scene=scene,
        template=RAW_SUPERHEROIC,
    )

    # The kb pushes bob off the rooftop (since rooftop edge is at x=15, target
    # at x=12, KB is +x direction, distance 20m → ends at x=32 which is outside
    # the roof polygon → falling resolves to ground (z=0).
    assert res.fall is not None
    assert res.fall.fall_distance_m == 12.0
    assert res.fall.landed_at.z == 0.0
