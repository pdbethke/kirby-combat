"""Climbing rates, status tokens and combat penalties — 6E1 p70, 6E2 p48-49.

These numbers arrived in the engine with no tests of their own: the only
coverage was a 731-line driver integration test in kirby-api that stayed
behind, so the rulebook values themselves were never asserted anywhere.

That matters more than usual here, because the two cited passages CONTRADICT
each other and the module picks a side. 6E1 p70 summarises the penalty as
"OCV and DCV are halved". The detailed treatment it defers to, 6E2 p48-49,
says DCV only, no OCV penalty, and adds a -2 DC penalty 6E1 omits entirely.
The module implements 6E2. These tests pin that choice so it cannot be
"corrected" back to 6E1 by someone reading only the summary.
"""
from kirby_combat import climbing


def test_base_climb_rate_is_two_metres_per_phase():
    # 6E1 p70: base climbing speed is 2m per Phase, at most.
    assert climbing.CLIMB_BASE_M == 2.0


def test_the_optional_faster_rule_buys_one_step_only():
    # 6E1 p70 allows +2m per -3 to the roll and lets the GM cap how far it
    # goes. This codebase caps it at a single step: 4m for -3, never 6m for -6.
    assert climbing.CLIMB_FAST_M == 4.0
    assert climbing.CLIMB_FAST_PENALTY == -3
    assert climbing.CLIMB_FAST_M == climbing.CLIMB_BASE_M * 2


def test_climb_status_names_the_face_being_climbed():
    # The token must identify WHICH wall: a combatant on the south face is
    # not in the same position as one on the east face.
    assert climbing.climb_status("wall-7") == "climbing:wall-7"
    assert climbing.climb_status("wall-7").startswith(climbing.CLIMB_STATUS_PREFIX)


def test_climbing_wall_id_recovers_the_face_from_a_status_set():
    statuses = {"stunned", climbing.climb_status("building_south_face"), "prone"}
    assert climbing.climbing_wall_id(statuses) == "building_south_face"


def test_climbing_wall_id_is_none_when_not_climbing():
    assert climbing.climbing_wall_id({"stunned", "prone"}) is None
    assert climbing.climbing_wall_id(set()) is None


def test_an_ordinary_face_costs_one_dcv_and_no_damage():
    # 6E2 p48-49, ordinary difficulty.
    m = climbing.climb_modifiers(0)
    assert m.dcv_delta == -1
    assert m.dcv_multiplier == 1.0
    assert m.dc_penalty == 0


def test_a_difficult_face_halves_dcv_and_costs_two_damage_classes():
    # 6E2 p48-49, difficult. Note it HALVES rather than subtracting.
    m = climbing.climb_modifiers(1)
    assert m.dcv_multiplier == 0.5
    assert m.dcv_delta == 0
    assert m.dc_penalty == -2


def test_climbing_never_penalises_ocv():
    """The 6E1-vs-6E2 disagreement, pinned.

    6E1 p70 says a climbing character's OCV and DCV are both halved. 6E2
    p48-49, which 6E1 explicitly defers to, penalises DCV only. This module
    implements 6E2, so no OCV field exists to penalise -- if one is ever
    added, this test should be revisited with a ruling, not deleted.
    """
    import dataclasses

    fields = {f.name for f in dataclasses.fields(climbing.ClimbModifiers)}
    assert fields == {"dcv_multiplier", "dcv_delta", "dc_penalty"}
    assert not any("ocv" in f for f in fields)
