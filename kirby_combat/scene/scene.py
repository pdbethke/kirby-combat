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
    ed_value: int | None = None             # ED, when it differs from PD (6E2 p173)
    resistant: bool = True                  # False = Normal Defense, not applied vs Killing
    #: The obj_id of the structure this wall is a FACE of, when it is one.
    #: Nothing else in the data could tell a boarding-house wall from a
    #: stack of whiskey barrels: both are `Wall`, both block, both have
    #: BODY. It decides what happens when the BODY runs out --- a face is
    #: BREACHED (a hole you can shoot through) and the building stands;
    #: anything else is simply destroyed. See `kirby_combat.collapse`.
    part_of: str | None = None
    walkable_width_m: float = 0.0           # 0 = nothing to stand on
    # 6E1 p70: None = cannot be climbed; 0 = ordinary (a ladder — no Climbing
    # Skill needed); > 0 = difficult, and subtracts from the Climbing roll.
    climb_difficulty: int | None = None

    @property
    def pd(self) -> int | None:
        """Physical defense. `def_value` has always meant PD; this names it."""
        return self.def_value

    @property
    def ed(self) -> int | None:
        """Energy defense, falling back to PD when the wall does not state
        one. The fallback is what keeps every pre-existing wall -- here and
        in kirby-api, which constructs these by keyword -- behaving exactly
        as it did before PD and ED were separated."""
        return self.def_value if self.ed_value is None else self.ed_value


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


#: 6E2 p.45's cover is about how much of a target can be seen. A standing
#: man is about two metres, so anything shorter is something he shoots
#: over --- which is what makes a wagon cover rather than a wall.
SEE_OVER_M = 2.0


@dataclass(frozen=True)
class Furnishing:
    """A solid thing standing on the ground, described by its FOOTPRINT.

    Scenery in this engine has only ever been a `Wall`: a segment and a
    height. That is right for the side of a building and wrong for
    everything you can walk around --- a wagon, a stack of barrels, a
    crate pile, a boulder, a parked car --- and three separate defects
    came out of the same missing fact.

    THE RENDERER GUESSED. `wallToBox` draws every wall 0.4 m thick,
    a constant with nothing behind it, because a line has no width to
    read. A wagon drawn 0.4 m across reads as a plank; drawn its real
    width it swallowed three of the Earps, because a line occupies no
    ground and nothing could refuse them.

    MEN STOOD INSIDE THE FURNITURE. Measured at the O.K. Corral: Wyatt
    0.40 m from the wagon's line, Virgil 0.50, Morgan 0.82.

    AND DURABILITY WAS TYPED IN BY HAND, wall by wall, while
    `kirby_terrain.OBJECT_DURABILITY` --- 6E2 p.173's own Objects Table
    --- sat there carrying DEF and BODY for eighteen materials.

    One footprint answers all three, which is why this is one type and
    not three patches.

    THE MODEL IS A SKIN AND THE FOOTPRINT IS THE TRUTH. `model` names a
    glTF for a renderer that wants one --- the format Dungeon Alchemist's
    own asset importer takes, and the one three.js loads natively, so the
    same file serves both. Nothing in the rules ever reads it: cover,
    line of sight, where a man may stand and what a bullet has to chew
    through all come from the polygon and the height.
    """
    id: str
    name: str
    #: Footprint on the ground, CCW, in metres. THE authoritative shape.
    polygon_xy: list[tuple[float, float]]
    height_m: float
    #: Keyed to `kirby_terrain.OBJECT_DURABILITY` (6E2 p.173). None is
    #: allowed only when the numbers are given outright --- the table is
    #: walls, doors and glass, and has no row for a wagon or a tree.
    material: str | None = None
    #: 6E2 p.172: the table is "a baseline the GM should change to fit the
    #: adventure", so an override is the rule and not a hack.
    pd: int | None = None
    ed: int | None = None
    body: int | None = None
    cover_level: int = 2
    blocks_movement: bool = True
    #: None means "decide from the height": you can see over a wagon and
    #: not over a stack of crates. An author who says otherwise is
    #: describing a thicket, and wins.
    blocks_los_override: bool | None = None
    #: A glTF/GLB for the renderer. Never read by any rule.
    model: str | None = None
    #: Can somebody strong enough pick this up and throw it?
    #:
    #: `Construct.portable` has existed since `pickup` was first written
    #: and carries the note that portability "is a PROPERTY OF THE
    #: OBJECT, not a kind of object" -- the fix for a filter on a
    #: `kind == "debris"` that nothing ever created. That fix left a
    #: second break one layer down: nothing a SCENE can author was ever
    #: portable, because this field did not exist. Every barrel, crate
    #: and wagon took the Construct default of False, so `pickup` and
    #: `throw_object` stayed two action kinds that could never fire.
    #:
    #: Defaults False: a building must not become liftable by omission.
    portable: bool = False

    def __post_init__(self) -> None:
        if len(self.polygon_xy) < 3:
            raise ValueError(
                f"{self.id}: a footprint needs at least three corners, "
                f"got {len(self.polygon_xy)}"
            )
        if self.material is None:
            missing = [n for n, v in
                       (("pd", self.pd), ("ed", self.ed), ("body", self.body))
                       if v is None]
            if missing:
                raise ValueError(
                    f"{self.id}: no material named, so {', '.join(missing)} "
                    f"must be given outright --- 6E2 p.173's table covers "
                    f"walls, doors and glass and has no row for this"
                )
        else:
            from kirby_terrain import OBJECT_DURABILITY

            if self.material not in OBJECT_DURABILITY:
                raise ValueError(
                    f"{self.id}: {self.material!r} is not in the Objects "
                    f"Table (6E2 p.173)"
                )

    @property
    def _table(self):
        from kirby_terrain import OBJECT_DURABILITY

        return OBJECT_DURABILITY.get(self.material) if self.material else None

    @property
    def pd_value(self) -> int:
        return self.pd if self.pd is not None else self._table.pd

    @property
    def ed_value(self) -> int:
        return self.ed if self.ed is not None else self._table.ed

    @property
    def body_value(self) -> int:
        return self.body if self.body is not None else self._table.body

    @property
    def blocks_los(self) -> bool:
        """You can see over a wagon and not over a stack of crates.

        Derived from the height against `SEE_OVER_M` rather than authored,
        because an author writing both a height and a sight flag can write
        a two-metre wall you can see over and never notice.
        """
        if self.blocks_los_override is not None:
            return self.blocks_los_override
        return self.height_m >= SEE_OVER_M

    #: How an edge's wall id is built. The prefix is what makes the
    #: projection idempotent — see `Scene.__post_init__`.
    EDGE_ID = "{id}#edge{n}"

    def as_walls(self) -> list["Wall"]:
        """This footprint as the wall segments its edges already are.

        TWELVE MODULES ASK `scene.walls` about movement, line of sight,
        visibility, cover moves, collapse, knockback and Area Of Effect.
        Authoring a wagon as a Furnishing and stopping there would
        silently REMOVE all of it: you could walk through the thing,
        nobody could take cover behind it, and it would not stop a blast.

        So the footprint projects, which is the move `constructs_in`
        already makes in the other direction and its own words for it ---
        "a second VIEW of the same geometry rather than a second copy of
        it". Each edge carries the furnishing's height, cover and
        durability, and `part_of` says which thing it is a face of, so a
        shot at one plank does not destroy the wagon.
        """
        corners = list(self.polygon_xy)
        walls: list[Wall] = []
        for n, (a, b) in enumerate(zip(corners, corners[1:] + corners[:1])):
            walls.append(Wall(
                id=self.EDGE_ID.format(id=self.id, n=n),
                name=self.name,
                segment=(Position(a[0], a[1], 0.0), Position(b[0], b[1], 0.0)),
                height_m=self.height_m,
                blocks_los=self.blocks_los,
                blocks_movement=self.blocks_movement,
                cover_level=self.cover_level,
                body=self.body_value,
                def_value=self.pd_value,
                ed_value=self.ed_value,
                part_of=self.id,
            ))
        return walls

    def occupies(self, x: float, y: float) -> bool:
        """Whether this thing is standing on that spot.

        The question a line could never answer, and the reason a man could
        stand inside a wagon.
        """
        from kirby_combat.scene.geometry import point_in_polygon_xy

        return point_in_polygon_xy((x, y), self.polygon_xy)

    @property
    def centre_xy(self) -> tuple[float, float]:
        xs = [p[0] for p in self.polygon_xy]
        ys = [p[1] for p in self.polygon_xy]
        return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

    @property
    def length_m(self) -> float:
        """The longer side of the footprint's bounding box."""
        return max(self._extent_x, self._extent_y)

    @property
    def width_m(self) -> float:
        """The shorter side --- the number the renderer had to invent."""
        return min(self._extent_x, self._extent_y)

    @property
    def _extent_x(self) -> float:
        xs = [p[0] for p in self.polygon_xy]
        return max(xs) - min(xs)

    @property
    def _extent_y(self) -> float:
        ys = [p[1] for p in self.polygon_xy]
        return max(ys) - min(ys)


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
    #: Solid things standing on the ground, described by their FOOTPRINT
    #: rather than by a line --- a wagon, a barrel stack, a boulder. See
    #: `Furnishing` for the three defects a line could not avoid.
    furnishings: list["Furnishing"] = field(default_factory=list)
    # 6E2 p.8, "COMBAT AND NONCOMBAT TIME": precise (Segment-level) time is
    # only tracked when a sequence needs it. A Scene at rest -- a house,
    # five occupants doing chores -- has no Encounter at all; this is that
    # normal, resting state, not an omission. Set only when the scene needs
    # Segment-level accounting (a fight, a car chase, a rocket countdown).
    encounter: "Encounter | None" = None

    def __post_init__(self) -> None:
        """Project every furnishing's footprint into `walls`.

        DONE HERE, not asked of the author, because an author who has to
        remember is an author who will forget, and forgetting means a
        wagon nothing can bump into.

        IDEMPOTENT, which matters more than it looks: `dataclasses
        .replace` rebuilds a Scene every time anybody moves, so this runs
        constantly and must not grow the wall list each time. An edge is
        recognised by its `part_of`.
        """
        already = {w.part_of for w in self.walls if w.part_of}
        for f in self.furnishings:
            if f.id in already:
                continue
            self.walls = list(self.walls) + f.as_walls()

    @property
    def furnishing_ids(self) -> frozenset[str]:
        """Every id that names a Furnishing.

        THREE CONSUMERS ASK THE SAME QUESTION. A footprint projects into
        four wall segments so movement and line of sight keep working,
        and every reader of `walls` then has to know those four are one
        object: the Brief listed a wagon four times with contradictory
        cover advice, `constructs_in` offered it as five separate things
        to shoot, and the front end drew a fence around it. So the SCENE
        answers it once rather than each consumer keeping its own copy
        and drifting.
        """
        return frozenset(f.id for f in self.furnishings)

    def is_furnishing_edge(self, wall) -> bool:
        """Whether this wall is one side of a Furnishing's footprint.

        Matched on `part_of`, which BUILDING faces carry too --- and they
        must keep counting: somebody authored "C.S. Fly's photograph
        gallery" separately from the boarding house wall because a
        fighter relates to them separately, and shooting out one wall of
        a building is a real tactic. Only an id naming a FURNISHING folds.
        """
        owner = getattr(wall, "part_of", None)
        return owner is not None and owner in self.furnishing_ids

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
