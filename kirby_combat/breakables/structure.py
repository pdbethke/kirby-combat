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
    """Mutable graph of supporter -> supported relationships.

    Support is REDUNDANT: an element stands while enough of its supporters
    remain intact. `required_supporters` names how many an element needs;
    anything unlisted needs one, so a lone column holding a floor behaves as
    it always did, while two columns sharing that floor now share the load.
    """
    links: list[StructuralLink] = field(default_factory=list)
    load_bearing_ids: set[str] = field(default_factory=set)
    #: element_id -> how many intact supporters it needs to stand (default 1).
    #: A GM wanting "the dome needs all three pillars" sets it to 3.
    required_supporters: dict[str, int] = field(default_factory=dict)

    def is_load_bearing(self, element_id: str) -> bool:
        return element_id in self.load_bearing_ids

    def supported_by(self, supporter_id: str) -> list[str]:
        return [l.supported_id for l in self.links if l.supporter_id == supporter_id]

    def supporters_of(self, supported_id: str) -> list[str]:
        """Every element holding `supported_id` up."""
        return [l.supporter_id for l in self.links if l.supported_id == supported_id]

    def required_support(self, element_id: str) -> int:
        """How many intact supporters `element_id` needs. Defaults to one."""
        return self.required_supporters.get(element_id, 1)


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
    already_destroyed: Iterable[str] | None = None,
) -> CascadeResult:
    """Compute the cascade of collapses triggered by destroying `destroyed_id`.

    Only load-bearing destructions cascade. Non-load-bearing destructions
    just register the destruction with no cascade events.

    A supported element collapses only when its INTACT supporters fall below
    what it requires (`StructuralGraph.required_support`, one by default).
    Two columns holding a mezzanine therefore share the load: dropping one
    leaves it standing, and dropping the second brings it down.

    `already_destroyed` carries the elements a previous attack removed, so a
    structure worn down across several phases converges. Without it every call
    starts from an intact building and the second column would never finish
    the job.

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

    # BFS through the support graph. `gone` is everything no longer holding
    # anything up — what a previous attack removed, plus what this one does.
    gone: set[str] = set(already_destroyed or ()) | {destroyed_id}
    queue = [destroyed_id]
    visited: set[str] = {destroyed_id}
    while queue:
        cur = queue.pop(0)
        for supported in graph.supported_by(cur):
            if supported in visited:
                continue
            intact = [s for s in graph.supporters_of(supported) if s not in gone]
            needed = graph.required_support(supported)
            if len(intact) >= needed:
                audit.append(
                    f"{supported} stands: {len(intact)} intact supporter(s) "
                    f"({', '.join(sorted(intact))}), needs {needed}"
                )
                continue
            visited.add(supported)
            gone.add(supported)
            events.append(CollapseEvent(element_id=supported, reason="supporter_lost"))
            audit.append(
                f"{supported} collapsed: {len(intact)} intact supporter(s), "
                f"needs {needed} (lost {cur})"
            )
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
