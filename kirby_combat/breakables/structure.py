"""Structure integrity cascade — load-bearing walls and supported surfaces.

When a load-bearing wall is destroyed, surfaces it supports collapse. Combatants
on collapsed surfaces trigger falling resolution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class StructuralLink:
    """A "X supports Y" relationship between structural elements."""
    supporter_id: str            # wall or surface id
    supported_id: str            # surface id


@dataclass
class StructuralGraph:
    """Mutable graph of supporter -> supported relationships."""
    links: list[StructuralLink] = field(default_factory=list)
    load_bearing_ids: set[str] = field(default_factory=set)

    def is_load_bearing(self, element_id: str) -> bool:
        return element_id in self.load_bearing_ids

    def supported_by(self, supporter_id: str) -> list[str]:
        return [l.supported_id for l in self.links if l.supporter_id == supporter_id]


@dataclass
class CollapseEvent:
    """One element of a cascade — a single collapse step."""
    element_id: str
    reason: str            # "directly_destroyed" | "supporter_lost"


@dataclass
class CascadeResult:
    """Result of a structural cascade triggered by an initial destruction."""
    initial_destroyed_id: str
    cascade_events: list[CollapseEvent]
    affected_combatants: list[str]
    triggered_falling_for: list[str]
    audit: list[str] = field(default_factory=list)


def cascade_destruction(
    graph: StructuralGraph,
    destroyed_id: str,
    combatants_on_surfaces: dict[str, list[str]] | None = None,
) -> CascadeResult:
    """Compute the cascade of collapses triggered by destroying `destroyed_id`.

    Only load-bearing destructions cascade. Non-load-bearing destructions
    just register the destruction with no cascade events.

    `combatants_on_surfaces` maps surface_id -> list of combatant ids on that
    surface; combatants on collapsed surfaces are returned in
    `triggered_falling_for`.
    """
    audit: list[str] = []
    events: list[CollapseEvent] = [
        CollapseEvent(element_id=destroyed_id, reason="directly_destroyed")
    ]
    affected: list[str] = []
    falling: list[str] = []
    combatants_on_surfaces = combatants_on_surfaces or {}

    # Surface combatants standing on the destroyed surface itself fall too.
    if destroyed_id in combatants_on_surfaces:
        for cid in combatants_on_surfaces[destroyed_id]:
            affected.append(cid)
            falling.append(cid)

    if not graph.is_load_bearing(destroyed_id):
        audit.append(f"{destroyed_id} not load-bearing; no cascade")
        return CascadeResult(
            initial_destroyed_id=destroyed_id,
            cascade_events=events,
            affected_combatants=affected,
            triggered_falling_for=falling,
            audit=audit,
        )

    # BFS through the support graph
    queue = [destroyed_id]
    visited: set[str] = {destroyed_id}
    while queue:
        cur = queue.pop(0)
        for supported in graph.supported_by(cur):
            if supported in visited:
                continue
            visited.add(supported)
            events.append(CollapseEvent(element_id=supported, reason="supporter_lost"))
            audit.append(f"{supported} collapsed (supporter {cur} lost)")
            if supported in combatants_on_surfaces:
                for cid in combatants_on_surfaces[supported]:
                    affected.append(cid)
                    falling.append(cid)
            queue.append(supported)

    return CascadeResult(
        initial_destroyed_id=destroyed_id,
        cascade_events=events,
        affected_combatants=affected,
        triggered_falling_for=falling,
        audit=audit,
    )


def make_environmental_event_payload(result: CascadeResult) -> dict[str, object]:
    """Translate a cascade result into an EnvironmentalTriggered event payload."""
    return {
        "kind": "structural_cascade",
        "initial_id": result.initial_destroyed_id,
        "collapsed_ids": [e.element_id for e in result.cascade_events],
        "falling_combatants": list(result.triggered_falling_for),
    }
