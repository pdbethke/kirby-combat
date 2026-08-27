"""status_deltas / apply_event_with_deltas -- pure diff surface for
publishing status change (status-emission Task 4).

CONTROLLER OVERRIDE: the task-4 brief asked for this to be wired inside
`apply_event`. It is not -- see the module docstring in
`kirby_combat/session/status_emission.py` for why (kirby-api's own
sequence bookkeeping would desync). This file tests the pure diff
function instead, plus a regression proving `apply_event`'s sequence
contract is exactly as strict as before this branch.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions.entangle import Entangle
from kirby_combat.actions.reactive.abort import mark_aborting
from kirby_combat.dice import FakeRoller
from kirby_combat.session import CombatSession, apply_event
from kirby_combat.session.events import SegmentAdvanced, make_author_engine
from kirby_combat.session.status_emission import (
    apply_event_with_deltas, status_deltas,
)
from kirby_combat.statuses import ABORTED, ENTANGLED, KNOCKED_OUT
from kirby_combat.template import CombatTemplate


def _c(id_: str, **overrides) -> "object":
    kwargs = dict(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=20, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=3,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    kwargs.update(overrides)
    return synthetic_combatant(**kwargs)


def _session(*combatants) -> CombatSession:
    return CombatSession.create(
        id="s1",
        combatants=list(combatants),
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


# ---------------------------------------------------------------------------
# A change produces the right id in `added`.
# ---------------------------------------------------------------------------

def test_new_condition_appears_in_added():
    before = _session(_c("alice"), _c("bob"))
    after, _ = Entangle.apply(
        before, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    deltas = status_deltas(before, after, session_id="s1", start_sequence=1)
    assert len(deltas) == 1
    evt = deltas[0]
    assert evt.combatant_id == "bob"
    assert evt.added == frozenset({ENTANGLED})
    assert evt.removed == frozenset()


# ---------------------------------------------------------------------------
# A condition ending produces it in `removed`.
# ---------------------------------------------------------------------------

def test_ended_condition_appears_in_removed():
    entangled_session, _ = Entangle.apply(
        _session(_c("alice"), _c("bob")),
        attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    escaped_session, _ = Entangle.escape_attempt(
        entangled_session, target_id="bob", str_used=100, escape_type="full",
    )

    deltas = status_deltas(
        entangled_session, escaped_session, session_id="s1", start_sequence=1,
    )
    assert len(deltas) == 1
    evt = deltas[0]
    assert evt.combatant_id == "bob"
    assert evt.removed == frozenset({ENTANGLED})
    assert evt.added == frozenset()


# ---------------------------------------------------------------------------
# An unchanged combatant produces no event at all.
# ---------------------------------------------------------------------------

def test_unchanged_combatant_produces_no_event():
    before = _session(_c("alice"), _c("bob"))
    # alice's status set is untouched by this Entangle of bob.
    after, _ = Entangle.apply(
        before, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    deltas = status_deltas(before, after, session_id="s1", start_sequence=1)
    assert all(evt.combatant_id != "alice" for evt in deltas)


def test_fully_identical_sessions_produce_no_events():
    s = _session(_c("alice"), _c("bob"))
    assert status_deltas(s, s, session_id="s1", start_sequence=1) == []


# ---------------------------------------------------------------------------
# Several combatants changing produce one event each.
# ---------------------------------------------------------------------------

def test_several_combatants_changing_each_get_one_event():
    before = _session(_c("alice"), _c("bob"), _c("carol"))
    mid, _ = Entangle.apply(
        before, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    after, _ = mark_aborting(mid, "carol", to_action="dodge")

    deltas = status_deltas(before, after, session_id="s1", start_sequence=1)
    by_id = {evt.combatant_id: evt for evt in deltas}
    assert set(by_id) == {"bob", "carol"}
    assert by_id["bob"].added == frozenset({ENTANGLED})
    assert by_id["carol"].added == frozenset({ABORTED})
    # sequential, gap-free numbering from start_sequence
    assert sorted(evt.sequence for evt in deltas) == [1, 2]


# ---------------------------------------------------------------------------
# A combatant with several simultaneous changes gets them all in one event.
# ---------------------------------------------------------------------------

def test_simultaneous_changes_collapse_into_one_event():
    before = _session(_c("alice"), _c("bob"))
    entangled, _ = Entangle.apply(
        before, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    after, _ = mark_aborting(entangled, "bob", to_action="dodge")

    deltas = status_deltas(before, after, session_id="s1", start_sequence=1)
    assert len(deltas) == 1
    evt = deltas[0]
    assert evt.combatant_id == "bob"
    assert evt.added == frozenset({ENTANGLED, ABORTED})
    assert evt.removed == frozenset()


# ---------------------------------------------------------------------------
# Combatants present in only one session.
# ---------------------------------------------------------------------------

def test_combatant_only_in_after_reports_its_statuses_as_added():
    before = _session(_c("alice"))
    after = _session(_c("alice"), _c("bob", current_stun=0))
    deltas = status_deltas(before, after, session_id="s1", start_sequence=1)
    assert len(deltas) == 1
    evt = deltas[0]
    assert evt.combatant_id == "bob"
    assert evt.added == frozenset({KNOCKED_OUT})
    assert evt.removed == frozenset()


def test_combatant_only_in_before_reports_its_statuses_as_removed():
    before = _session(_c("alice"), _c("bob", current_stun=0))
    after = _session(_c("alice"))
    deltas = status_deltas(before, after, session_id="s1", start_sequence=1)
    assert len(deltas) == 1
    evt = deltas[0]
    assert evt.combatant_id == "bob"
    assert evt.removed == frozenset({KNOCKED_OUT})
    assert evt.added == frozenset()


def test_combatant_only_in_one_session_with_no_statuses_produces_no_event():
    before = _session(_c("alice"))
    after = _session(_c("alice"), _c("bob"))  # bob joins with a clean slate
    deltas = status_deltas(before, after, session_id="s1", start_sequence=1)
    assert deltas == []


# ---------------------------------------------------------------------------
# id/timestamp/author construction.
# ---------------------------------------------------------------------------

def test_well_formed_events_have_session_id_and_default_engine_author():
    before = _session(_c("alice"), _c("bob"))
    after, _ = Entangle.apply(
        before, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    deltas = status_deltas(before, after, session_id="s1", start_sequence=7)
    evt = deltas[0]
    assert evt.session_id == "s1"
    assert evt.sequence == 7
    assert evt.author.type == "engine"
    assert evt.id  # non-empty, generated
    assert isinstance(evt.timestamp, datetime)


def test_custom_id_factory_is_honoured():
    before = _session(_c("alice"), _c("bob"))
    after, _ = Entangle.apply(
        before, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    deltas = status_deltas(
        before, after, session_id="s1", start_sequence=1,
        id_factory=lambda seq, cid: f"custom-{cid}-{seq}",
    )
    assert deltas[0].id == "custom-bob-1"


# ---------------------------------------------------------------------------
# Recursion is a non-issue: diffing across the emitted events themselves
# finds nothing further.
# ---------------------------------------------------------------------------

def test_diffing_across_the_emitted_events_finds_nothing_further():
    before = _session(_c("alice"), _c("bob"))
    after, _ = Entangle.apply(
        before, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    deltas = status_deltas(
        before, after, session_id="s1", start_sequence=len(after.event_log) + 1,
    )
    assert len(deltas) == 1

    # Append the emitted event to `after`'s log via the untouched
    # apply_event, then diff again from that new state: statuses_for does
    # not read StatusEffectsChanged, so nothing changed and no new delta
    # appears.
    appended = apply_event(after, deltas[0])
    second_pass = status_deltas(
        after, appended, session_id="s1", start_sequence=len(appended.event_log) + 1,
    )
    assert second_pass == []


# ---------------------------------------------------------------------------
# apply_event_with_deltas: convenience wrapper.
# ---------------------------------------------------------------------------

def test_apply_event_with_deltas_returns_session_and_deltas_uncommitted():
    s = _session(_c("alice"), _c("bob"))
    evt = SegmentAdvanced(
        id="evt-x", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=12, to_segment=1, to_turn=2,
    )
    new_session, deltas = apply_event_with_deltas(s, evt)
    assert new_session.timeline.segment == 1
    assert deltas == []  # SegmentAdvanced changes no combatant's status set
    # Deltas are not appended -- only the applied event is in the log.
    assert len(new_session.event_log) == len(s.event_log) + 1


# ---------------------------------------------------------------------------
# REGRESSION: apply_event's sequence contract is unaffected by this branch.
# ---------------------------------------------------------------------------

def test_apply_event_sequence_contract_is_unaffected_by_status_emission():
    """The whole point of the controller override: apply_event still
    raises on a sequence mismatch, still accepts exactly the next
    sequence, and still appends exactly one event per call -- regardless
    of anything status_deltas / apply_event_with_deltas does."""
    s = _session(_c("alice"), _c("bob"))

    good = SegmentAdvanced(
        id="evt-1", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=12, to_segment=1, to_turn=2,
    )
    s2 = apply_event(s, good)
    assert len(s2.event_log) == len(s.event_log) + 1  # exactly one appended

    stale = SegmentAdvanced(
        id="evt-2", session_id="s1", sequence=len(s.event_log) + 1,  # stale
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=1, to_segment=2, to_turn=2,
    )
    with pytest.raises(ValueError, match="sequence"):
        apply_event(s2, stale)
