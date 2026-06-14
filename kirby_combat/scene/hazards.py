"""Hazard trigger detection — find which hazards fire on combatant moves/ticks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from kirby_combat.scene.scene import Hazard, HazardEffect, Position, Scene
from kirby_combat.scene.geometry import (
    point_in_polygon_xy, path_crosses_polygon,
)


TriggerReason = Literal["entered", "passed_through", "in_zone_during_tick"]


@dataclass(frozen=True)
class HazardTriggerResult:
    hazard_id: str
    affected_combatants: list[str]
    effect: HazardEffect
    trigger_reason: TriggerReason


def _within_elevation(z: float, elevation_range_m: tuple[float, float]) -> bool:
    lo, hi = elevation_range_m
    return lo <= z <= hi


def compute_hazard_triggers(
    *,
    scene: Scene,
    combatant_positions_before: dict[str, Position],
    combatant_positions_after: dict[str, Position],
    phase: Literal["movement", "segment_tick"],
) -> list[HazardTriggerResult]:
    """Return one HazardTriggerResult per (hazard, set-of-affected-combatants).

    Behavior depends on hazard.trigger:
      - "on_enter": combatant was outside in _before, inside in _after
      - "on_pass": the line from before.xy to after.xy crosses any polygon edge
      - "every_segment": combatant is inside in _after AND phase == "segment_tick"

    Elevation filter applies to all triggers: `combatant.z` must be within
    `hazard.elevation_range_m`.
    """
    results: list[HazardTriggerResult] = []

    for hazard in scene.hazards:
        affected: list[str] = []
        for cid in combatant_positions_after.keys():
            after_pos = combatant_positions_after[cid]
            if not _within_elevation(after_pos.z, hazard.elevation_range_m):
                continue
            after_inside = point_in_polygon_xy(
                (after_pos.x, after_pos.y), hazard.polygon_xy,
            )

            if hazard.trigger == "every_segment":
                if phase != "segment_tick":
                    continue
                if after_inside:
                    affected.append(cid)
                continue

            if hazard.trigger == "on_enter":
                before_pos = combatant_positions_before.get(cid)
                before_inside = (
                    before_pos is not None
                    and _within_elevation(before_pos.z, hazard.elevation_range_m)
                    and point_in_polygon_xy(
                        (before_pos.x, before_pos.y), hazard.polygon_xy,
                    )
                )
                if after_inside and not before_inside:
                    affected.append(cid)
                continue

            if hazard.trigger == "on_pass":
                before_pos = combatant_positions_before.get(cid)
                if before_pos is None:
                    # No prior position: only triggers if currently inside
                    if after_inside:
                        affected.append(cid)
                    continue
                if not _within_elevation(before_pos.z, hazard.elevation_range_m):
                    # Was at wrong elevation; only trigger if entered now
                    if after_inside:
                        affected.append(cid)
                    continue
                # Path-crossing test
                if path_crosses_polygon(
                    (before_pos.x, before_pos.y),
                    (after_pos.x, after_pos.y),
                    hazard.polygon_xy,
                ):
                    affected.append(cid)
                elif after_inside:
                    # Edge case: started already inside (e.g., placed there)
                    affected.append(cid)
                continue

        if affected:
            reason: TriggerReason = (
                "in_zone_during_tick" if hazard.trigger == "every_segment"
                else "entered" if hazard.trigger == "on_enter"
                else "passed_through"
            )
            results.append(HazardTriggerResult(
                hazard_id=hazard.id,
                affected_combatants=affected,
                effect=hazard.effect,
                trigger_reason=reason,
            ))

    return results
