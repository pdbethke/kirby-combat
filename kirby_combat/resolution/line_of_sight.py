"""Line-of-sight gating for ranged attacks.

Composes scene.geometry.line_of_sight_clear (raycast against walls) with the
Indirect advantage carve-out per 6E1 p339 §USING INDIRECT POWERS IN COMBAT.

Per 6E1 p339:
    "Indirect does not allow an attacker to bypass a target's personal
     defenses [...] The purpose of Indirect is to get the Source Point of
     the attack on the other side of the obstacle, or to create a Path for
     the attack that bypasses the obstacle to hit the target point."

The engine encodes this as a single boolean: indirect_advantage = True
means LoS is automatic for the attack-targeting check (the wall doesn't
block aiming). Personal defenses still apply; that's handled by the
defense pipeline, not here.

Cover OCV modifiers are NOT applied here — that's `scene.cover` after the
LoS gate succeeds. This module's only job is the boolean: can the attack
even be made?
"""
from __future__ import annotations

from kirby_combat.scene.geometry import first_blocking_wall, line_of_sight_clear
from kirby_combat.scene.scene import Position, Scene, Wall


def has_line_of_sight(
    scene: Scene,
    attacker_pos: Position,
    target_pos: Position,
    *,
    indirect_advantage: bool = False,
) -> bool:
    """Return True iff the attacker has LoS to the target.

    Walls in `scene.walls` with blocks_los=True can break LoS. Wall height is
    respected (per scene.geometry.line_of_sight_clear).

    If `indirect_advantage` is True, LoS is unconditionally True per
    6E1 p339 §Indirect — the attacker may aim around obstacles via an
    altered Source Point.
    """
    if indirect_advantage:
        return True
    return line_of_sight_clear(attacker_pos, target_pos, scene.walls)


def gate_ranged_attack(
    scene: Scene,
    attacker_pos: Position,
    target_pos: Position,
    *,
    is_ranged: bool,
    indirect_advantage: bool = False,
) -> bool:
    """Boolean gate for whether a ranged attack may target the target.

    HTH attacks (is_ranged=False) bypass this check — adjacency is handled
    elsewhere (you cannot HTH-strike a combatant on the other side of a wall;
    you simply have no path to reach them, which is a movement concern not a
    LoS concern).

    Returns True if:
      - Attack is HTH (is_ranged=False), OR
      - Indirect advantage is set, OR
      - line_of_sight_clear succeeds.
    """
    if not is_ranged:
        return True
    return has_line_of_sight(
        scene, attacker_pos, target_pos,
        indirect_advantage=indirect_advantage,
    )


def blocking_wall_for_shot(
    scene: Scene,
    attacker_pos: Position,
    target_pos: Position,
    *,
    is_ranged: bool,
    indirect_advantage: bool = False,
) -> "Wall | None":
    """The wall a ranged shot is redirected into when LoS is blocked, or None.

    HTH (is_ranged=False) and Indirect never redirect. The driver (kirby-api)
    applies object damage to the returned wall and deals nothing to the target.
    """
    if not is_ranged or indirect_advantage:
        return None
    return first_blocking_wall(attacker_pos, target_pos, scene.walls)
