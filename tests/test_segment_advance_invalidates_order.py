"""Advancing the Segment must not leave a stale acting order behind.

`Timeline.acting_order` is a list of `ActingSlot`s built FOR ONE SEGMENT --
each slot carries the `segment` it was resolved for. `run_segment` writes
it; nothing used to clear it. So a session that advanced past the Segment
its order was built for kept serving that order, with its `has_acted` flags,
to anyone who read the timeline.

Nothing caught this because nothing consumed `acting_order` in a loop: the
turn loop lived in the parked kirby-api driver and tracked its own cursor in
the database. The engine's own loop reads this field, so a stale order would
mean replaying an earlier Segment's participants -- silently, and with their
`has_acted` flags already set.

HALF OF THE DOCUMENTED PROBLEM WAS ALREADY FIXED. `encounter.py` carried a
worked example claiming `run_segment@3` then three `advance_segment` calls
leaves `enc.segment=6` against `tl.segment=3`. Measured 2026-09-06: the two
clocks agree (both 6), because `advance_segment` emits `SegmentAdvanced` and
`apply_event` syncs `timeline.segment`/`turn` from it. What did NOT agree
was the acting order, which still described Segment 3.
"""
from __future__ import annotations

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.encounter import Encounter
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


def _f(id: str, dex: int):
    return synthetic_combatant(
        id=id, name=id, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=dex, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=40, max_body=15, max_end=30,
        current_stun=40, current_body=15, current_end=30,
    )


def _encounter(segment: int = 3) -> Encounter:
    session = CombatSession.create(
        id="s", combatants=[_f("a", 20), _f("b", 15)], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
    ).start()
    return Encounter(id="e", turn=1, segment=segment, sessions=[session])


def test_run_segment_writes_an_order_for_the_current_segment():
    enc = _encounter(segment=3).run_segment(roller=lambda: 10)
    tl = enc.sessions[0].timeline
    assert tl.segment == 3
    assert [s.segment for s in tl.acting_order] == [3, 3]


def test_advancing_one_segment_clears_the_previous_order():
    enc = _encounter(segment=3).run_segment(roller=lambda: 10)
    enc = enc.advance_segment()

    tl = enc.sessions[0].timeline
    assert tl.segment == 4
    assert tl.acting_order == [], "Segment 3's order survived into Segment 4"
    assert tl.current_slot_index == 0


def test_the_worked_example_from_encounter_py():
    """`run_segment@3` then three advances. Both clocks read 6, and the
    order no longer claims to describe Segment 3."""
    enc = _encounter(segment=3).run_segment(roller=lambda: 10)
    for _ in range(3):
        enc = enc.advance_segment()

    tl = enc.sessions[0].timeline
    assert enc.segment == 6
    assert tl.segment == 6, "the two clocks must agree"
    assert tl.acting_order == [], "a Segment 3 order must not describe Segment 6"


def test_the_turn_wrap_also_clears_the_order():
    enc = _encounter(segment=12).run_segment(roller=lambda: 10)
    assert enc.sessions[0].timeline.acting_order  # sanity: there was one

    enc = enc.advance_segment()          # 12 -> Turn 2 Segment 1

    tl = enc.sessions[0].timeline
    assert (enc.turn, enc.segment) == (2, 1)
    assert (tl.turn, tl.segment) == (2, 1)
    assert tl.acting_order == []


def test_has_acted_flags_cannot_leak_across_segments():
    """The flags are the sharp edge: a surviving order would carry its
    `has_acted=True` marks into the next Segment, so a combatant who acted
    in Segment 3 would read as already-acted in Segment 4 and be skipped."""
    enc = _encounter(segment=3).run_segment(roller=lambda: 10)
    session = enc.sessions[0]
    session.timeline.acting_order[0].has_acted = True
    enc = enc.advance_segment()

    assert enc.sessions[0].timeline.acting_order == []
