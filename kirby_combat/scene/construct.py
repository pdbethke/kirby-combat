"""Unified placed-entity model. A Construct is a destructible/effect-bearing
region of the scene — walls, hazard zones, force walls, (reserved) illusion
zones are all Constructs. Spec 2026-06-09 §1.1.

The engine reasons over Constructs for durability + effect resolution; the
authored Wall/Hazard dataclasses (scene.py) remain the template source and
project into Constructs via the helpers here. Frozen: a Construct's `body` is
the CURRENT body for one resolution; damage flows out as events and back via
kirby-api hydration on the next step.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from kirby_combat.scene.scene import Position, Wall, Hazard

EffectKind = Literal["damage", "suffocation", "status", "mental"]  # "mental" reserved (v1: not resolved)
EffectGating = Literal["physical_def", "breathing_swimming", "mental_disbelief", "none"]
EffectTrigger = Literal["on_enter", "on_pass", "every_segment", "passive"]
ConstructKind = Literal["wall", "hazard_zone", "force_wall", "illusion_zone"]  # illusion_zone reserved
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
    # durability (both None => indestructible). `body` is CURRENT body.
    def_value: int | None = None
    body: int | None = None
    # effect / provenance
    effect: ConstructEffect | None = None
    source_combatant_id: str | None = None
    created_at_seq: int | None = None

    @property
    def destructible(self) -> bool:
        return self.def_value is not None and self.body is not None


def construct_from_wall(wall: Wall) -> Construct:
    """Project an authored Wall into a Construct. `def_value` rides Wall.def_value
    (None on legacy walls with no authored DEF)."""
    return Construct(
        obj_id=wall.id, kind="wall",
        segment=wall.segment, height_m=wall.height_m,
        blocks_los=wall.blocks_los, blocks_movement=wall.blocks_movement,
        permeability="impermeable" if wall.blocks_movement else "porous",
        cover_level=wall.cover_level,
        def_value=wall.def_value, body=wall.body,
    )


def construct_from_hazard(hazard: Hazard) -> Construct:
    """Project a legacy authored Hazard into a hazard_zone Construct (porous,
    physical-DEF-gated damage or a status). Suffocation hazards are authored as
    Constructs directly by kirby-api, not via the legacy Hazard model."""
    eff = hazard.effect
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
