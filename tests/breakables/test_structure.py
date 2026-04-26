"""Structure integrity cascade — load-bearing collapse."""
import pytest

from kirby_combat.breakables.structure import (
    StructuralGraph, StructuralLink,
    cascade_destruction, make_environmental_event_payload,
)


def _graph() -> StructuralGraph:
    """A simple structure: wall_A supports floor1; floor1 supports floor2."""
    return StructuralGraph(
        links=[
            StructuralLink("wall_A", "floor1"),
            StructuralLink("floor1", "floor2"),
        ],
        load_bearing_ids={"wall_A", "floor1"},
    )


def test_load_bearing_wall_destruction_cascades_to_supported_surfaces():
    g = _graph()
    r = cascade_destruction(g, "wall_A")
    collapsed = [e.element_id for e in r.cascade_events]
    assert "wall_A" in collapsed
    assert "floor1" in collapsed
    assert "floor2" in collapsed


def test_supported_surface_drops_elevation_when_support_fails():
    g = _graph()
    r = cascade_destruction(g, "wall_A")
    # All supported surfaces flagged in cascade
    reasons = {e.element_id: e.reason for e in r.cascade_events}
    assert reasons["wall_A"] == "directly_destroyed"
    assert reasons["floor1"] == "supporter_lost"
    assert reasons["floor2"] == "supporter_lost"


def test_combatants_on_collapsed_surface_trigger_falling():
    g = _graph()
    r = cascade_destruction(
        g, "wall_A",
        combatants_on_surfaces={"floor1": ["alice"], "floor2": ["bob"]},
    )
    assert "alice" in r.triggered_falling_for
    assert "bob" in r.triggered_falling_for


def test_non_load_bearing_wall_destruction_no_cascade():
    g = StructuralGraph(
        links=[StructuralLink("wall_A", "floor1")],
        load_bearing_ids=set(),  # nothing load-bearing
    )
    r = cascade_destruction(g, "wall_A")
    assert len(r.cascade_events) == 1   # just the wall itself
    assert r.cascade_events[0].element_id == "wall_A"


def test_structure_emits_environmentaltriggered_events():
    g = _graph()
    r = cascade_destruction(g, "wall_A",
                            combatants_on_surfaces={"floor1": ["alice"]})
    payload = make_environmental_event_payload(r)
    assert payload["kind"] == "structural_cascade"
    assert payload["initial_id"] == "wall_A"
    assert "alice" in payload["falling_combatants"]
