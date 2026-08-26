"""Tests for Encounter -- the engine's Segment/Turn clock."""
from kirby_combat.encounter import Encounter


def test_advancing_within_a_turn_increments_the_segment():
    e = Encounter(id="e1", turn=1, segment=3)
    assert e.advance_segment().segment == 4


def test_segment_12_wraps_to_segment_1_of_the_next_turn():
    """6E2 p.18: a Turn consists of 12 Segments."""
    e = Encounter(id="e1", turn=1, segment=12)
    nxt = e.advance_segment()
    assert (nxt.turn, nxt.segment) == (2, 1)


def test_a_new_encounter_starts_on_segment_12():
    """6E2 p.20: combat always begins on Segment 12."""
    assert Encounter(id="e1").segment == 12


def test_advance_returns_a_new_encounter_and_does_not_mutate():
    e = Encounter(id="e1", turn=1, segment=3)
    e.advance_segment()
    assert e.segment == 3


def test_an_encounter_can_exist_with_no_sessions():
    """6E2 p.8 allows a precisely-timed sequence that is not a fight
    ("or some other sequence you need to detail precisely")."""
    assert Encounter(id="e1").sessions == []
