"""Line-of-sight gating for ranged attacks. Per 6E1 p339 §Indirect."""
from __future__ import annotations

from kirby_combat.resolution.line_of_sight import (
    has_line_of_sight, gate_ranged_attack,
)
from kirby_combat.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.scene.cover import compute_cover_level, cover_ocv_modifier


def _scene_with(walls=None, surfaces=None) -> Scene:
    return Scene(
        id="s1", name="Test",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=list(surfaces or []),
        walls=list(walls or []),
        hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )


def _wall(x: float = 10.0, height: float = 3.0, blocks_los: bool = True) -> Wall:
    return Wall(
        id="w", name="Brick",
        segment=(Position(x, 0, 0), Position(x, 10, 0)),
        height_m=height, blocks_los=blocks_los, blocks_movement=True,
        cover_level=4, body=6,
    )


def test_ranged_attack_blocked_when_no_los_to_target():
    """A wall that intersects the attacker→target ray and is tall enough blocks LoS."""
    scene = _scene_with(walls=[_wall(x=10.0, height=3.0)])
    attacker = Position(0, 5, 1.5)
    target = Position(20, 5, 1.5)
    assert has_line_of_sight(scene, attacker, target) is False
    # And gate_ranged_attack agrees.
    assert gate_ranged_attack(
        scene, attacker, target, is_ranged=True, indirect_advantage=False
    ) is False


def test_ranged_attack_at_cover_applies_ocv_penalty_from_cover_level():
    """When cover applies but doesn't fully block (here: short wall, shooter above),
    LoS is clear yet cover OCV penalty applies via the cover module.

    Combine LoS gating with cover_ocv_modifier so callers can verify the two
    layers compose correctly: LoS first (boolean), then OCV adjustment.
    """
    short_wall = Wall(
        id="w", name="Low",
        segment=(Position(10, 0, 0), Position(10, 10, 0)),
        height_m=1.0,
        blocks_los=True, blocks_movement=True,
        cover_level=2, body=4,
    )
    scene = _scene_with(walls=[short_wall])
    # Shooter at z=2 (above short wall top), target at z=1.5 — LoS clears
    attacker = Position(0, 5, 2.0)
    target = Position(20, 5, 1.5)
    assert has_line_of_sight(scene, attacker, target) is True

    # The standard 50% cover bucket → -2 OCV per 6E2 p45.
    assert cover_ocv_modifier(50) == -2


def test_hth_attack_unaffected_by_los_when_adjacent():
    """HTH attacks are not gated by LoS — adjacency / pathing is movement, not LoS."""
    scene = _scene_with(walls=[_wall(x=10.0, height=3.0)])
    attacker = Position(0, 5, 1.5)
    target = Position(20, 5, 1.5)
    # HTH bypasses regardless of walls between
    assert gate_ranged_attack(
        scene, attacker, target, is_ranged=False
    ) is True


def test_indirect_power_advantage_bypasses_los_requirement():
    """Per 6E1 p339, Indirect lets the attack work despite intervening walls."""
    scene = _scene_with(walls=[_wall(x=10.0, height=10.0)])  # tall wall, total block
    attacker = Position(0, 5, 1.5)
    target = Position(20, 5, 1.5)
    # Without Indirect, blocked.
    assert gate_ranged_attack(
        scene, attacker, target, is_ranged=True, indirect_advantage=False
    ) is False
    # With Indirect, allowed.
    assert gate_ranged_attack(
        scene, attacker, target, is_ranged=True, indirect_advantage=True
    ) is True


def test_ranged_attack_clear_when_no_walls():
    scene = _scene_with()
    attacker = Position(0, 5, 1.5)
    target = Position(20, 5, 1.5)
    assert has_line_of_sight(scene, attacker, target) is True
    assert gate_ranged_attack(scene, attacker, target, is_ranged=True) is True
