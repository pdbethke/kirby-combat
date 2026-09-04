"""Unified placed-entity model. A Construct is a destructible/effect-bearing
region of the scene — walls, hazard zones, force walls, (reserved) illusion
zones are all Constructs. Spec 2026-06-09 §1.1.

The engine reasons over Constructs for durability + effect resolution; the
authored Wall/Hazard dataclasses (scene.py) remain the template source and
project into Constructs via the helpers here. Frozen: a Construct's `body` is
the CURRENT body for one resolution; damage flows out as events and back via
driver hydration on the next step.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from kirby_combat.scene.scene import Position, Wall, Hazard
from kirby_combat.scene.geometry import point_in_polygon_xy

EffectKind = Literal["damage", "suffocation", "status", "mental"]  # "mental" reserved (v1: not resolved)
EffectGating = Literal["physical_def", "breathing_swimming", "mental_disbelief", "none"]
EffectTrigger = Literal["on_enter", "on_pass", "every_segment", "passive"]
ConstructKind = Literal["wall", "hazard_zone", "force_wall", "illusion_zone", "darkness_zone"]  # illusion_zone reserved
Permeability = Literal["porous", "impermeable"]


@dataclass(frozen=True)
class ConstructEffect:
    """A defense-gated consequence for occupants/passers of a Construct."""
    kind: EffectKind
    gating: EffectGating = "none"
    trigger: EffectTrigger = "passive"
    damage_dice: int = 0
    damage_type: str = "normal"
    status_inflicted: str | None = None


@dataclass(frozen=True)
class Construct:
    """An independently placed region with optional durability and effect."""
    obj_id: str
    kind: ConstructKind
    # geometry: a segment (walls/barriers) OR a polygon (zones) — exactly one
    segment: tuple[Position, Position] | None = None
    polygon_xy: list[tuple[float, float]] | None = None
    elevation_range_m: tuple[float, float] = (0.0, 0.0)
    height_m: float = 0.0
    # blocking / cover
    blocks_los: bool = False
    blocks_movement: bool = False
    permeability: Permeability = "porous"
    cover_level: int = 0
    #: Levels of "Cannot Be Escaped With Teleportation" on the source
    #: Barrier (6E1 p175): a teleport path may not pass this construct
    #: unless the Teleportation carries at least as many levels of
    #: Armor Piercing (movement_legality gates on it). 0 = no effect.
    no_teleport_levels: int = 0
    # durability (both None => indestructible). `body` is CURRENT body.
    def_value: int | None = None
    ed_value: int | None = None             # ED, when it differs from PD (6E2 p173)
    resistant: bool = True                  # False = Normal Defense, not applied vs Killing
    body: int | None = None
    # effect / provenance
    effect: ConstructEffect | None = None
    source_combatant_id: str | None = None
    created_at_seq: int | None = None
    # sense-affecting (darkness_zone): the Sense Group this zone occludes
    # (e.g. "sight", "mental") and whether the creating combatant sees through it.
    sense_group: str | None = None
    creator_immune: bool = False

    @property
    def destructible(self) -> bool:
        return self.def_value is not None and self.body is not None

    @property
    def pd(self) -> int | None:
        """Physical defense. `def_value` has always meant PD; this names it."""
        return self.def_value

    @property
    def ed(self) -> int | None:
        """Energy defense, falling back to PD when the construct does not state
        one. The fallback is what keeps every pre-existing construct -- here and
        in kirby-api, which constructs these by keyword -- behaving exactly
        as it did before PD and ED were separated."""
        return self.def_value if self.ed_value is None else self.ed_value


def construct_from_spawn_spec(
    *,
    obj_id: str,
    kind: "ConstructKind",
    segment: "tuple[Position, Position] | None" = None,
    polygon_xy: "list[tuple[float, float]] | None" = None,
    elevation_range_m: "tuple[float, float]" = (0.0, 0.0),
    height_m: float = 0.0,
    def_value: "int | None" = None,
    body: "int | None" = None,
    effect: "ConstructEffect | None" = None,
    permeability: "Permeability | None" = None,
    source_combatant_id: "str | None" = None,
    created_at_seq: "int | None" = None,
    sense_group: "str | None" = None,
    creator_immune: bool = False,
) -> "Construct":
    """Build a spawned Construct (force wall / spawn-on-destroy hazard). A
    force_wall defaults to a LoS+movement blocking impermeable barrier; a
    hazard_zone defaults to porous. the driver computes def/body/geometry from the
    casting power (Plan 2) and passes them here. Spec §1.7."""
    if permeability is None:
        permeability = "impermeable" if kind in ("wall", "force_wall") else "porous"
    blocks = kind in ("wall", "force_wall")
    return Construct(
        obj_id=obj_id, kind=kind, segment=segment, polygon_xy=polygon_xy,
        elevation_range_m=elevation_range_m, height_m=height_m,
        blocks_los=blocks, blocks_movement=blocks, permeability=permeability,
        cover_level=4 if blocks else 0,
        def_value=def_value, body=body, effect=effect,
        source_combatant_id=source_combatant_id, created_at_seq=created_at_seq,
        sense_group=sense_group, creator_immune=creator_immune,
    )


def constructs_containing(pos: "Position", constructs: "Iterable[Construct]") -> "list[Construct]":
    """Return constructs whose polygon contains `pos` in xy within their elevation
    range (segment constructs are never 'containing' a point)."""
    out: list[Construct] = []
    for c in constructs:
        if c.polygon_xy is None:
            continue
        lo, hi = c.elevation_range_m
        if not (lo <= pos.z <= hi):
            continue
        if point_in_polygon_xy((pos.x, pos.y), c.polygon_xy):
            out.append(c)
    return out


def construct_from_wall(wall: Wall) -> Construct:
    """Project an authored Wall into a Construct. `def_value` rides Wall.def_value
    (None on legacy walls with no authored DEF)."""
    return Construct(
        obj_id=wall.id, kind="wall",
        segment=wall.segment, height_m=wall.height_m,
        blocks_los=wall.blocks_los, blocks_movement=wall.blocks_movement,
        permeability="impermeable" if wall.blocks_movement else "porous",
        cover_level=wall.cover_level,
        def_value=wall.def_value, ed_value=wall.ed_value, resistant=wall.resistant,
        body=wall.body,
    )


def construct_from_hazard(hazard: Hazard) -> Construct:
    """Project a legacy authored Hazard into a hazard_zone Construct (porous,
    physical-DEF-gated damage or a status). Suffocation hazards are authored as
    Constructs directly by the driver, not via the legacy Hazard model."""
    eff = hazard.effect
    if not eff.damage_dice and not eff.status_inflicted:
        raise ValueError(
            f"Hazard {hazard.id!r}: HazardEffect has neither damage_dice nor "
            "status_inflicted — nothing to project into a Construct effect"
        )
    kind: EffectKind = "damage" if eff.damage_dice else "status"
    return Construct(
        obj_id=hazard.id, kind="hazard_zone",
        polygon_xy=list(hazard.polygon_xy), elevation_range_m=hazard.elevation_range_m,
        permeability="porous",
        effect=ConstructEffect(
            kind=kind,
            gating="physical_def" if kind == "damage" else "none",
            trigger=hazard.trigger,
            damage_dice=eff.damage_dice, damage_type=eff.damage_type,
            status_inflicted=eff.status_inflicted,
        ),
    )
