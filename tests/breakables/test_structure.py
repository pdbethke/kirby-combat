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


# --- redundant support -------------------------------------------------------
#
# A supported element stands while enough of its supporters remain. Before
# this, losing ANY supporter collapsed it, so two columns holding one floor
# behaved exactly like one column — which is not how buildings, or players,
# expect load to work.


def _two_columns() -> StructuralGraph:
    """Two columns share the mezzanine; the mezzanine holds the roof."""
    return StructuralGraph(
        links=[
            StructuralLink("column_a", "mezzanine"),
            StructuralLink("column_b", "mezzanine"),
            StructuralLink("mezzanine", "roof"),
        ],
        load_bearing_ids={"column_a", "column_b", "mezzanine"},
    )


def test_losing_one_of_two_supporters_does_not_collapse_the_supported():
    r = cascade_destruction(_two_columns(), "column_a")
    collapsed = [e.element_id for e in r.cascade_events]
    assert collapsed == ["column_a"], "the mezzanine still has column_b"


def test_combatants_above_a_surviving_element_do_not_fall():
    r = cascade_destruction(
        _two_columns(), "column_a",
        combatants_on_surfaces={"mezzanine": ["sniper"], "roof": ["lookout"]},
    )
    assert r.triggered_falling_for == []


def test_losing_the_second_supporter_collapses_it_and_everything_above():
    """The first column is already gone; taking the second finishes the job."""
    r = cascade_destruction(
        _two_columns(), "column_b",
        combatants_on_surfaces={"mezzanine": ["sniper"], "roof": ["lookout"]},
        already_destroyed={"column_a"},
    )
    collapsed = [e.element_id for e in r.cascade_events]
    assert collapsed == ["column_b", "mezzanine", "roof"]
    assert sorted(r.triggered_falling_for) == ["lookout", "sniper"]


def test_destroying_the_supported_element_itself_still_cascades_upward():
    r = cascade_destruction(_two_columns(), "mezzanine")
    collapsed = [e.element_id for e in r.cascade_events]
    assert collapsed == ["mezzanine", "roof"], "the roof had only the mezzanine"


def test_a_required_supporter_count_above_one_collapses_early():
    """A GM can say an element needs 2 of its 3 supports; losing one is enough."""
    g = StructuralGraph(
        links=[
            StructuralLink("pillar_1", "dome"),
            StructuralLink("pillar_2", "dome"),
            StructuralLink("pillar_3", "dome"),
        ],
        load_bearing_ids={"pillar_1", "pillar_2", "pillar_3"},
        required_supporters={"dome": 3},
    )
    r = cascade_destruction(g, "pillar_1")
    assert [e.element_id for e in r.cascade_events] == ["pillar_1", "dome"]


def test_the_default_requirement_is_one_supporter():
    g = _two_columns()
    assert g.required_support("mezzanine") == 1
    assert g.required_support("anything_unlisted") == 1


def test_supporters_of_reports_every_supporter():
    assert sorted(_two_columns().supporters_of("mezzanine")) == ["column_a", "column_b"]
