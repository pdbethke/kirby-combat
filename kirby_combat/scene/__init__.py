"""Scene — 3D terrain and environmental context for combat."""
from kirby_combat.scene.scene import (
    Scene, SceneBounds, Surface, Wall, Hazard, HazardEffect,
    Position, AmbientConditions,
)
from kirby_combat.scene.construct import (
    Construct, ConstructEffect, construct_from_wall, construct_from_hazard,
)

__all__ = [
    "Scene", "SceneBounds", "Surface", "Wall", "Hazard", "HazardEffect",
    "Position", "AmbientConditions",
    "Construct", "ConstructEffect", "construct_from_wall", "construct_from_hazard",
]
