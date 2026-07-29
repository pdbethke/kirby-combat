"""Scene — 3D terrain and environmental context for combat."""
from kirby_combat.scene.scene import (
    Scene, SceneBounds, Surface, Wall, Hazard, HazardEffect,
    Position, AmbientConditions, wall_top_surface, is_climbable,
)
from kirby_combat.scene.construct import (
    Construct, ConstructEffect, construct_from_wall, construct_from_hazard,
    construct_from_spawn_spec, constructs_containing,
)
from kirby_combat.scene.effects import ConstructEffectResult, resolve_construct_effect
from kirby_combat.scene.movement_legality import mode_requires_support

__all__ = [
    "Scene", "SceneBounds", "Surface", "Wall", "Hazard", "HazardEffect",
    "Position", "AmbientConditions", "wall_top_surface", "is_climbable",
    "Construct", "ConstructEffect", "construct_from_wall", "construct_from_hazard",
    "construct_from_spawn_spec", "constructs_containing",
    "ConstructEffectResult", "resolve_construct_effect",
    "mode_requires_support",
]
