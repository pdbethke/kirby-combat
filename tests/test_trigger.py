"""Trigger power activation — match conditions against events, decrement charges.

Per 6E1 p366-368 §Trigger.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from kirby_combat.actions.trigger import (
    Trigger, TriggerCondition, check_triggers, recharge_trigger,
)
from kirby_combat.session.events import (
    ActionResolved, AdjustmentApplied, SegmentAdvanced, make_author_engine,
)


def _segment_advanced(to_segment: int = 5) -> SegmentAdvanced:
    return SegmentAdvanced(
        id=str(uuid.uuid4()), session_id="s1", sequence=1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=12, to_segment=to_segment, to_turn=2,
    )


def _action_resolved(payload: dict | None = None) -> ActionResolved:
    return ActionResolved(
        id=str(uuid.uuid4()), session_id="s1", sequence=1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        declaration_event_id="prev",
        result_payload=payload or {},
    )


def _trigger(
    *,
    tid: str = "t1",
    owner: str = "alice",
    event_type: str = "ActionResolved",
    matches: dict | None = None,
    charges: int | None = None,
    rechargeable: bool = False,
) -> Trigger:
    return Trigger(
        id=tid, owner_id=owner,
        condition=TriggerCondition(event_type=event_type, matches=matches or {}),
        action_template={"action_type": "stored_blast"},
        charges=charges, rechargeable=rechargeable,
    )


# ---------------------------------------------------------------------------
# Core matching
# ---------------------------------------------------------------------------

def test_trigger_fires_on_matching_condition_event():
    t = _trigger(event_type="SegmentAdvanced", matches={"to_segment": 5})
    new_triggers, firings = check_triggers([t], _segment_advanced(to_segment=5))
    assert len(firings) == 1
    assert firings[0].trigger_id == "t1"
    assert firings[0].action_template == {"action_type": "stored_blast"}
    # fires_count incremented
    assert new_triggers[0].fires_count == 1


def test_trigger_does_not_fire_on_non_matching_event():
    t = _trigger(event_type="SegmentAdvanced", matches={"to_segment": 5})
    new_triggers, firings = check_triggers([t], _segment_advanced(to_segment=7))
    assert firings == []
    assert new_triggers[0].fires_count == 0
    # Also doesn't fire on a different event class entirely
    new_triggers, firings = check_triggers([t], _action_resolved())
    assert firings == []


# ---------------------------------------------------------------------------
# Charges & recharge
# ---------------------------------------------------------------------------

def test_trigger_with_charges_decrements_on_fire():
    t = _trigger(event_type="SegmentAdvanced", matches={"to_segment": 5}, charges=3)
    triggers = [t]
    for expected_charges in (2, 1, 0):
        triggers, firings = check_triggers(triggers, _segment_advanced(5))
        assert len(firings) == 1
        assert triggers[0].charges == expected_charges
    # Fourth attempt: charges depleted → no fire
    triggers, firings = check_triggers(triggers, _segment_advanced(5))
    assert firings == []


def test_trigger_reset_condition_rechargeable():
    t = _trigger(
        event_type="SegmentAdvanced", matches={"to_segment": 5},
        charges=2, rechargeable=True,
    )
    triggers = [t]
    triggers, _ = check_triggers(triggers, _segment_advanced(5))
    triggers, _ = check_triggers(triggers, _segment_advanced(5))
    assert triggers[0].charges == 0

    # Now recharge
    triggers = recharge_trigger(triggers, "t1")
    assert triggers[0].charges == 2
    assert triggers[0].fires_count == 0

    # And fire again
    triggers, firings = check_triggers(triggers, _segment_advanced(5))
    assert len(firings) == 1
    assert triggers[0].charges == 1


def test_recharge_non_rechargeable_raises():
    t = _trigger(charges=1, rechargeable=False)
    triggers = [t]
    triggers, _ = check_triggers(triggers, _action_resolved())
    try:
        recharge_trigger(triggers, "t1")
    except ValueError:
        return
    raise AssertionError("recharge_trigger should reject non-rechargeable triggers")


# ---------------------------------------------------------------------------
# Multiple triggers on same event
# ---------------------------------------------------------------------------

def test_multiple_triggers_on_same_condition_all_fire():
    t1 = _trigger(tid="t1", event_type="SegmentAdvanced", matches={"to_segment": 5})
    t2 = _trigger(tid="t2", owner="bob",
                  event_type="SegmentAdvanced", matches={"to_segment": 5})
    t3 = _trigger(tid="t3", event_type="SegmentAdvanced", matches={"to_segment": 7})
    triggers = [t1, t2, t3]

    new_triggers, firings = check_triggers(triggers, _segment_advanced(5))
    fired_ids = sorted(f.trigger_id for f in firings)
    assert fired_ids == ["t1", "t2"]      # t3 doesn't match
    # Both matched triggers' fires_count incremented
    by_id = {t.id: t for t in new_triggers}
    assert by_id["t1"].fires_count == 1
    assert by_id["t2"].fires_count == 1
    assert by_id["t3"].fires_count == 0


def test_trigger_match_passes_action_template_to_firing():
    t = _trigger(event_type="ActionResolved")
    new_triggers, firings = check_triggers([t], _action_resolved({"key": "val"}))
    assert firings[0].action_template == {"action_type": "stored_blast"}


def test_trigger_with_missing_event_field_does_not_match():
    """If condition references a field the event doesn't have, no match."""
    t = _trigger(
        event_type="ActionResolved",
        matches={"to_segment": 5},   # ActionResolved has no to_segment field
    )
    new_triggers, firings = check_triggers([t], _action_resolved())
    assert firings == []


def test_trigger_matches_on_field_value_equality():
    """Standard 'all listed fields must equal expected' semantic."""
    t = _trigger(
        event_type="AdjustmentApplied",
        matches={"target_id": "alice", "stat": "str"},
    )
    matching = AdjustmentApplied(
        id="e1", session_id="s1", sequence=1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        target_id="alice", stat="str", delta=5, fade_rate_per_turn=5,
    )
    non_matching = AdjustmentApplied(
        id="e2", session_id="s1", sequence=1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        target_id="alice", stat="con", delta=5, fade_rate_per_turn=5,
    )
    _, firings_match = check_triggers([t], matching)
    _, firings_other = check_triggers([t], non_matching)
    assert len(firings_match) == 1
    assert firings_other == []
