"""Adjustments fade — the emitter that did not exist.

`AdjustmentFaded` has been declared in `session/events.py` since Adjustment
was written. `apply_event` passes it through. `session/effects.py` folds it.
And a grep for `AdjustmentFaded(` found ONLY the class definition -- nothing
ever constructed one, so an Aid or a Drain applied in this engine lasted
forever, where 6E1 p.133 and p.139 say both fade at Active Points per Turn.

The same "class + reducer exist, emitter does not" shape as the Krackle
`RecoveryTaken` finding, and the same reason it went unnoticed: a fold with
nothing to fold returns a perfectly good answer.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.encounter import Encounter
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.effects import adjustment_delta, adjustments_for
from kirby_combat.session.events import AdjustmentApplied, make_author_engine
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


def _session():
    fighters = [
        synthetic_combatant(
            id=name, name=name, ocv=8, dcv=8, omcv=5, dmcv=5,
            spd=4, dex=20, ego=15, str_=15, con=18, pre=15, rec=6,
            pd=5, ed=5, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
            max_stun=40, max_body=12, max_end=40,
            current_stun=40, current_body=12, current_end=40,
        )
        for name in ("alice", "bob")
    ]
    return CombatSession.create(
        id="s", combatants=fighters, scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
    ).start()


def _apply(session, target: str, delta: int, *, stat: str = "STUN", rate: int = 5):
    return apply_event(session, AdjustmentApplied(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        target_id=target, stat=stat, delta=delta, fade_rate_per_turn=rate,
    ))


def _wrap_turn(session, turns: int = 1):
    """Advance from Segment 12 through the wrap, `turns` times."""
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    for _ in range(turns):
        enc = enc.advance_segment()
        while enc.segment != 12:
            enc = enc.advance_segment()
    return enc.sessions[0]


# ---- It fades at all ----

def test_an_aid_fades_by_its_rate_each_turn():
    """6E1 p.133 -- 5 Active Points per Turn by default."""
    session = _apply(_session(), "alice", +12)
    assert adjustment_delta(session, "alice", "STUN") == 12

    session = _wrap_turn(session)
    assert adjustment_delta(session, "alice", "STUN") == 7

    session = _wrap_turn(session)
    assert adjustment_delta(session, "alice", "STUN") == 2


def test_a_drain_fades_toward_zero_and_never_flips_sign():
    """A Drain that kept 'fading' would start boosting the stat it
    drained."""
    session = _apply(_session(), "alice", -7)
    session = _wrap_turn(session)
    assert adjustment_delta(session, "alice", "STUN") == -2

    session = _wrap_turn(session)
    assert adjustment_delta(session, "alice", "STUN") == 0

    session = _wrap_turn(session)
    assert adjustment_delta(session, "alice", "STUN") == 0, "no overshoot"


def test_an_aid_smaller_than_its_rate_clears_in_one_turn():
    session = _wrap_turn(_apply(_session(), "alice", +3))
    assert adjustment_delta(session, "alice", "STUN") == 0


def test_a_bought_up_fade_rate_is_honoured():
    """The rate rides on the AdjustmentApplied that started it, so a power
    with a bought-up rate keeps its own."""
    session = _wrap_turn(_apply(_session(), "alice", +20, rate=10))
    assert adjustment_delta(session, "alice", "STUN") == 10


def test_a_zero_rate_never_fades():
    """Healing shares Aid's arithmetic but does not fade (6E1 p.150); a
    zero rate is how a non-fading adjustment says so."""
    session = _wrap_turn(_apply(_session(), "alice", +12, rate=0), turns=3)
    assert adjustment_delta(session, "alice", "STUN") == 12


# ---- The absolute-value discipline ----

def test_the_event_carries_the_RESULTING_value_not_the_amount_faded():
    """`session/effects.py` requires it of every state-changing event here,
    and it is why the fold can walk forward safely: AdjustmentFaded SETS
    the running total. A delta would be unrecoverable the moment one was
    missed."""
    session = _wrap_turn(_apply(_session(), "alice", +12))
    faded = [e for e in session.event_log if e.kind == "AdjustmentFaded"]
    assert len(faded) == 1
    assert faded[0].remaining_delta == 7, "the value it results in, not -5"


def test_fading_is_recorded_per_stat():
    session = _apply(_apply(_session(), "alice", +12), "alice", -9, stat="DEX")
    session = _wrap_turn(session)
    assert adjustment_delta(session, "alice", "STUN") == 7
    assert adjustment_delta(session, "alice", "DEX") == -4


def test_adjustments_do_not_bleed_between_combatants():
    session = _apply(_apply(_session(), "alice", +12), "bob", +20)
    session = _wrap_turn(session)
    assert adjustment_delta(session, "alice", "STUN") == 7
    assert adjustment_delta(session, "bob", "STUN") == 15


def test_two_aids_on_one_stat_fade_as_their_sum():
    """`adjustments_for` reports one entry per stat, so the fade applies to
    the net -- not once per application."""
    session = _apply(_apply(_session(), "alice", +6), "alice", +6)
    assert adjustment_delta(session, "alice", "STUN") == 12
    session = _wrap_turn(session)
    assert adjustment_delta(session, "alice", "STUN") == 7


def test_nothing_is_emitted_for_a_combatant_with_no_adjustment():
    session = _wrap_turn(_session())
    assert not [e for e in session.event_log if e.kind == "AdjustmentFaded"]


def test_a_spent_adjustment_stops_emitting():
    """Once it reaches zero there is nothing left to fade, and the log
    should not fill with no-op events every Turn."""
    session = _wrap_turn(_apply(_session(), "alice", +3), turns=4)
    faded = [e for e in session.event_log if e.kind == "AdjustmentFaded"]
    assert len(faded) == 1


def test_the_fade_belongs_to_the_turn_that_is_ending():
    """Logged before the SegmentAdvanced that closes the Turn, so a
    replayer's 'what Turn did this happen in' answer stays on the Turn it
    happened in -- the same ordering RecoveryTaken already required."""
    session = _wrap_turn(_apply(_session(), "alice", +12))
    kinds = [e.kind for e in session.event_log]
    assert kinds.index("AdjustmentFaded") < len(kinds) - 1
    assert "SegmentAdvanced" in kinds[kinds.index("AdjustmentFaded"):]


def test_the_effect_is_gone_from_the_summary_once_spent():
    session = _wrap_turn(_apply(_session(), "alice", +3))
    assert adjustments_for(session, "alice") == []
