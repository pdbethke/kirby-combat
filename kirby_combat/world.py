"""World — a setting containing many Scenes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.scene import Scene


@dataclass
class World:
    """A setting containing many Scenes.

    A World is a container for scenes — e.g., a street, a base, and a rooftop
    are three scenes in the same world. It holds no clock (the clock lives on
    Encounter, which is scene-scoped), no rules, and no relationships between
    scenes.
    """
    id: str
    name: str
    scenes: list[Scene] = field(default_factory=list)

    def scene_by_id(self, scene_id: str) -> Scene | None:
        """Return the scene with the given id, or None if not found."""
        for scene in self.scenes:
            if scene.id == scene_id:
                return scene
        return None
