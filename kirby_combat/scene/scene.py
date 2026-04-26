"""Scene — engine-authoritative 3D terrain + environment model."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal


@dataclass(frozen=True)
class Position:
    """3D position with facing. Meters + radians. 0 rad = east."""
    x: float
    y: float
    z: float
    facing: float = 0.0


@dataclass(frozen=True)
class SceneBounds:
    """Axis-aligned bounding box. Combatants must stay within."""
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float


@dataclass(frozen=True)
class AmbientConditions:
    """Scene-wide environmental conditions."""
    light_level: int = 4                    # 0 pitch dark → 4 full daylight
    gravity_scale: float = 1.0              # 1.0 = Earth normal
    weather: str | None = None              # None, "rain", "fog", "hurricane", ...


@dataclass(frozen=True)
class Surface:
    """A floor, rooftop, platform, or ground patch."""
    id: str
    name: str
    polygon_xy: list[tuple[float, float]]   # CCW vertex list
    elevation_m: float
    surface_type: Literal[
        "ground", "rooftop", "water", "ice", "rubble", "forest", "road", "sand"
    ]
    cover_level: int = 0                    # 0 (none) — 4 (full)
    is_supporting: bool = True              # False = combatants fall through


@dataclass(frozen=True)
class Wall:
    """A wall segment blocking movement and/or line of sight."""
    id: str
    name: str
    segment: tuple[Position, Position]
    height_m: float
    blocks_los: bool = True
    blocks_movement: bool = True
    cover_level: int = 4                    # partial cover granted to those behind
    body: int = 6                           # BODY to break through


@dataclass(frozen=True)
class HazardEffect:
    """What happens when a hazard triggers on a combatant."""
    damage_dice: int = 0
    damage_type: str = "normal"             # "normal" | "killing" | "energy" | "flash"
    status_inflicted: str | None = None     # "on_fire", "stunned", ...


@dataclass(frozen=True)
class Hazard:
    """A hazard zone that triggers effects on combatants."""
    id: str
    name: str
    polygon_xy: list[tuple[float, float]]
    elevation_range_m: tuple[float, float]
    trigger: Literal["on_enter", "on_pass", "every_segment"]
    effect: HazardEffect


@dataclass
class Scene:
    """Engine-authoritative scene. Mutable combatant_positions dict.

    Note: Scene itself is mutable (not frozen) so combatant positions can
    update in place via `place_combatant` returning a NEW scene via
    `dataclasses.replace`. The structural geometry (surfaces, walls, hazards)
    is immutable per Phase 2 design — those are frozen subtypes.
    """
    id: str
    name: str
    bounds: SceneBounds
    surfaces: list[Surface]
    walls: list[Wall]
    hazards: list[Hazard]
    ambient: AmbientConditions
    combatant_positions: dict[str, Position] = field(default_factory=dict)

    def place_combatant(self, combatant_id: str, position: Position) -> "Scene":
        """Return a new Scene with the combatant positioned.

        Raises ValueError if the position is outside the scene bounds on any axis.
        """
        if not (self.bounds.min_x <= position.x <= self.bounds.max_x):
            raise ValueError(
                f"position ({position.x},{position.y},{position.z}) out of bounds"
            )
        if not (self.bounds.min_y <= position.y <= self.bounds.max_y):
            raise ValueError(
                f"position ({position.x},{position.y},{position.z}) out of bounds"
            )
        if not (self.bounds.min_z <= position.z <= self.bounds.max_z):
            raise ValueError(
                f"position ({position.x},{position.y},{position.z}) out of bounds"
            )
        new_positions = dict(self.combatant_positions)
        new_positions[combatant_id] = position
        return replace(self, combatant_positions=new_positions)
