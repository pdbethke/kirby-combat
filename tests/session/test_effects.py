"""Persistent-effect state derivation + apply_event extension tests.

Per Plan 1 Task 24. The effects module derives Adjustment/Entangle/Flash state
from the event log; apply_event is the dispatcher that appends the events.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from kirby_dice import FakeRoller
from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.session import CombatSession, apply_event
from kirby_combat.session.effects import (
    adjustment_delta, adjustments_for, entangle_state, flash_state,
)
from kirby_combat.session.events import (
    AdjustmentApplied, AdjustmentFaded,
    EntangleApplied, EntangleEscape,
    FlashApplied, FlashRecovered,
    make_author_engine,
)
from kirby_combat.template import CombatTemplate


def _session() -> CombatSession:
    c = synthetic_combatant(
        id="alice", name="alice", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    return CombatSession.create(
        id="s1", combatants=[c], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def _emit(session: CombatSession, evt) -> CombatSession:
    return apply_event(session, evt)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Adjustment tests
# ---------------------------------------------------------------------------

def test_apply_adjustment_applied_mutates_combatant_stat():
    s = _session()
    evt = AdjustmentApplied(
        id=str(uuid.uuid4()), session_id="s1",
        sequence=len(s.event_log) + 1, timestamp=_now(),
        author=make_author_engine(),
        target_id="alice", stat="str", delta=10, fade_rate_per_turn=5,
    )
    s2 = _emit(s, evt)
    # The "mutation" is recoverable via the derivation helper.
    assert adjustment_delta(s2, "alice", "str") == 10


def test_apply_adjustment_faded_reverts_stat_by_fade_rate():
    s = _session()
    s = _emit(s, AdjustmentApplied(
        id=str(uuid.uuid4()), session_id="s1",
        sequence=len(s.event_log) + 1, timestamp=_now(),
        author=make_author_engine(),
        target_id="alice", stat="str", delta=10, fade_rate_per_turn=5,
    ))
    # Faded event sets the remaining_delta — represents one turn of fade.
    s = _emit(s, AdjustmentFaded(
        id=str(uuid.uuid4()), session_id="s1",
        sequence=len(s.event_log) + 1, timestamp=_now(),
        author=make_author_engine(),
        target_id="alice", stat="str", remaining_delta=5,
    ))
    assert adjustment_delta(s, "alice", "str") == 5


def test_multiple_adjustments_on_same_stat_sum_deltas():
    s = _session()
    for delta in (4, 3, 2):
        s = _emit(s, AdjustmentApplied(
            id=str(uuid.uuid4()), session_id="s1",
            sequence=len(s.event_log) + 1, timestamp=_now(),
            author=make_author_engine(),
            target_id="alice", stat="dex", delta=delta, fade_rate_per_turn=5,
        ))
    assert adjustment_delta(s, "alice", "dex") == 9
    effects = adjustments_for(s, "alice")
    dex_effect = next(e for e in effects if e.stat == "dex")
    assert dex_effect.net_delta == 9


# ---------------------------------------------------------------------------
# Entangle tests
# ---------------------------------------------------------------------------

def test_apply_entangle_applied_sets_combatant_entangle_state():
    s = _session()
    s = _emit(s, EntangleApplied(
        id=str(uuid.uuid4()), session_id="s1",
        sequence=len(s.event_log) + 1, timestamp=_now(),
        author=make_author_engine(),
        target_id="alice", entangle_body=8, entangle_pd=4, entangle_ed=4,
    ))
    state = entangle_state(s, "alice")
    assert state.is_entangled
    assert state.body_remaining == 8
    assert state.entangle_pd == 4


def test_apply_entangle_escape_clears_entangle_when_escaped_true():
    s = _session()
    s = _emit(s, EntangleApplied(
        id=str(uuid.uuid4()), session_id="s1",
        sequence=len(s.event_log) + 1, timestamp=_now(),
        author=make_author_engine(),
        target_id="alice", entangle_body=8, entangle_pd=4, entangle_ed=4,
    ))
    s = _emit(s, EntangleEscape(
        id=str(uuid.uuid4()), session_id="s1",
        sequence=len(s.event_log) + 1, timestamp=_now(),
        author=make_author_engine(),
        target_id="alice", method="full_str",
        damage_to_entangle_body=8, escaped=True,
    ))
    state = entangle_state(s, "alice")
    assert not state.is_entangled
    assert state.body_remaining == 0


# ---------------------------------------------------------------------------
# Flash tests
# ---------------------------------------------------------------------------

def test_apply_flash_applied_stacks_segments_on_existing_flash():
    s = _session()
    # First flash for sight: 3 segments
    s = _emit(s, FlashApplied(
        id=str(uuid.uuid4()), session_id="s1",
        sequence=len(s.event_log) + 1, timestamp=_now(),
        author=make_author_engine(),
        target_id="alice", sense_group="sight", segments=3,
    ))
    # Second flash for sight: +2 segments
    s = _emit(s, FlashApplied(
        id=str(uuid.uuid4()), session_id="s1",
        sequence=len(s.event_log) + 1, timestamp=_now(),
        author=make_author_engine(),
        target_id="alice", sense_group="sight", segments=2,
    ))
    state = flash_state(s, "alice")
    assert state.segments_by_sense["sight"] == 5
    assert state.is_flashed


def test_apply_flash_recovered_decrements_segments_remaining():
    s = _session()
    s = _emit(s, FlashApplied(
        id=str(uuid.uuid4()), session_id="s1",
        sequence=len(s.event_log) + 1, timestamp=_now(),
        author=make_author_engine(),
        target_id="alice", sense_group="hearing", segments=4,
    ))
    s = _emit(s, FlashRecovered(
        id=str(uuid.uuid4()), session_id="s1",
        sequence=len(s.event_log) + 1, timestamp=_now(),
        author=make_author_engine(),
        target_id="alice", sense_group="hearing", segments_remaining=3,
    ))
    state = flash_state(s, "alice")
    assert state.segments_by_sense.get("hearing", 0) == 3
