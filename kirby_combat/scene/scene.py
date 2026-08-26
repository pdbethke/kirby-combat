"""Scene — engine-authoritative 3D terrain + environment model."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from kirby_combat.encounter import Encounter
    from kirby_combat.scene.construct import Construct


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
    is_precarious: bool = False             # narrow footing — see footing rules
    # 6E1 p70: None = cannot be climbed; 0 = ordinary (a ladder — no Climbing
    # Skill needed); > 0 = difficult, and subtracts from the Climbing roll.
    climb_difficulty: int | None = None


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
    def_value: int | None = None            # resistant DEF an attack must beat (None = legacy/indestructible)
    walkable_width_m: float = 0.0           # 0 = nothing to stand on
    # 6E1 p70: None = cannot be climbed; 0 = ordinary (a ladder — no Climbing
    # Skill needed); > 0 = difficult, and subtracts from the Climbing roll.
    climb_difficulty: int | None = None


def is_climbable(obj: "Wall | Surface") -> bool:
    """True when `obj` declares any climbability at all (6E1 p70).

    `climb_difficulty is None` means no handholds exist — sheer glass, a force
    wall. Zero is NOT falsy here: it means an ordinary climb needing no Skill.
    """
    return getattr(obj, "climb_difficulty", None) is not None


# A walkway narrower than this is precarious footing.
_PRECARIOUS_WIDTH_M = 2.0


def wall_top_surface(wall: Wall) -> Surface | None:
    """The standable strip on top of `wall`, or None when the wall has no
    walkable width (a chain-link fence, a force wall, a low parapet).

    Derived rather than authored: walls are destructible, and the driver's
    hydration simply stops emitting a destroyed wall — so a derived strip
    disappears with its wall and can never desync from `height_m`.
    """
    if wall.walkable_width_m <= 0.0:
        return None
    a, b = wall.segment
    dx, dy = b.x - a.x, b.y - a.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None                     # degenerate wall: no strip
    # Unit normal to the segment in xy; the strip extends half the walkable
    # width to each side.
    nx, ny = -dy / length, dx / length
    h = wall.walkable_width_m / 2.0
    polygon = [
        (a.x + nx * h, a.y + ny * h),
        (a.x - nx * h, a.y - ny * h),
        (b.x - nx * h, b.y - ny * h),
        (b.x + nx * h, b.y + ny * h),
    ]
    return Surface(
        id=f"{wall.id}:top",
        name=f"{wall.name} top",
        polygon_xy=polygon,
        elevation_m=min(a.z, b.z) + wall.height_m,
        surface_type="rooftop",
        cover_level=0,
        is_supporting=True,
        is_precarious=wall.walkable_width_m < _PRECARIOUS_WIDTH_M,
    )


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
    constructs: list["Construct"] = field(default_factory=list)
    # 6E2 p.8, "COMBAT AND NONCOMBAT TIME": precise (Segment-level) time is
    # only tracked when a sequence needs it. A Scene at rest -- a house,
    # five occupants doing chores -- has no Encounter at all; this is that
    # normal, resting state, not an omission. Set only when the scene needs
    # Segment-level accounting (a fight, a car chase, a rocket countdown).
    encounter: "Encounter | None" = None

    def supporting_surfaces(self) -> list[Surface]:
        """Authored surfaces plus derived wall-top strips — THE support
        authority for this scene.

        Every "can something stand here" question routes through this, so
        movement legality, teleport legality, and fall resolution all agree
        about wall tops without any of them learning what a wall is.
        """
        out = list(self.surfaces)
        for wall in self.walls:
            strip = wall_top_surface(wall)
            if strip is not None:
                out.append(strip)
        return out

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
