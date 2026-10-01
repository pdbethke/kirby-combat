"""An Abort spends ONE Phase, and its bonus lasts one Phase past that.

6E2 p.24, "HOW TO ABORT AN ACTION", sets two different windows, and the
engine used to honour neither: `aborted_this_phase` was a one-way latch, so
a man who dodged once was "aborting" for the rest of the fight. He kept
his +3 DCV forever, he could never abort again, and the Phase he gave up
was never actually taken from him.

The two windows (paraphrased; see the page):

- LOCKOUT. Once he aborts, he can neither abort again nor act until the
  Phase he gave up has passed. In the book's SPD 4 example, a man who
  aborts his Segment 6 Phase in Segment 4 is locked through Segment 6 and
  free from Segment 7.
- BONUS. What he aborted to lasts until his next Phase AFTER the one he
  gave up. In the book's SPD 3 example, aborting the Segment 4 Phase in
  Segment 2 to Dodge keeps the DCV until his Phase in Segment 8.

And the Phase itself is GONE: Lazer (SPD 5) aborts in Segment 6, and "when
Segment 8 rolls around" he can do nothing, though the Dodge still guards
him; he next acts in Segment 10.

The windows are fixed when the abort is declared and travel on the
`AbortDeclared` event, so a fight replayed from its log expires them at
the same moments as the fight that ran.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions.reactive.abort import is_aborting
from kirby_combat.actions.reactive.dodge import Dodge
from kirby_combat.loop.run import _skip_reason
from kirby_combat.session import CombatSession
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import (
    ActingOrderResolved, PhaseSpent, SegmentAdvanced, make_author_engine,
)
from kirby_combat.statuses import ABORTED, statuses_for
from kirby_combat.template import CombatTemplate
from kirby_dice import FakeRoller


def _man(id_: str, spd: int, dex: int = 20):
    return synthetic_combatant(id=id_, name=id_, spd=spd, dex=dex)


def _session(*combatants) -> CombatSession:
    return CombatSession.create(
        id="s1",
        combatants=list(combatants),
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def _stamp(session: CombatSession) -> dict:
    return dict(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_engine(),
    )


def _to(session: CombatSession, segment: int, turn: int = 2) -> CombatSession:
    return apply_event(session, SegmentAdvanced(
        **_stamp(session),
        from_segment=session.timeline.segment,
        to_segment=segment,
        to_turn=turn,
    ))


def _order(session: CombatSession, *ids: str) -> CombatSession:
    return apply_event(session, ActingOrderResolved(
        **_stamp(session),
        order=list(ids),
        segment=session.timeline.segment,
        turn=session.timeline.turn,
    ))


def _spend(session: CombatSession, combatant_id: str) -> CombatSession:
    return apply_event(session, PhaseSpent(
        **_stamp(session),
        combatant_id=combatant_id,
        segment=session.timeline.segment,
        turn=session.timeline.turn,
    ))


def test_the_lockout_ends_when_the_aborted_phase_has_passed():
    """6E2 p.24: SPD 4 (Phases 3, 6, 9, 12) aborts his Segment 6 Phase in
    Segment 4. Locked in Segments 4, 5 and 6; free to abort again in 7."""
    session = _to(_session(_man("hero", spd=4)), 4)
    session, _ = Dodge.declare(session, "hero")

    for segment in (5, 6):
        session = _to(session, segment)
        assert is_aborting(session, "hero"), segment
        assert ABORTED in statuses_for(session, "hero"), segment
        with pytest.raises(ValueError):
            Dodge.declare(session, "hero")

    session = _to(session, 7)
    assert not is_aborting(session, "hero")
    assert ABORTED not in statuses_for(session, "hero")
    # "in Segment 7 or 8 he could Abort his Phase in Segment 9"
    session, evt = Dodge.declare(session, "hero")
    assert (evt.aborted_turn, evt.aborted_segment) == (2, 9)


def test_the_dodge_lasts_until_the_next_phase_after_the_one_given_up():
    """6E2 p.24: SPD 3 (Phases 4, 8, 12) in Segment 2 aborts his Segment 4
    Phase to Dodge; the +3 DCV lasts until his next Phase, Segment 8."""
    session = _to(_session(_man("hero", spd=3)), 2)
    session, evt = Dodge.declare(session, "hero")
    assert (evt.aborted_turn, evt.aborted_segment) == (2, 4)
    assert (evt.bonus_until_turn, evt.bonus_until_segment) == (2, 8)

    for segment in range(3, 9):
        session = _to(session, segment)
        assert Dodge.dcv_bonus(session, "hero") == 3, segment

    # Segment 8 is his Phase. The Dodge guards him until he takes it.
    session = _order(session, "hero")
    assert Dodge.dcv_bonus(session, "hero") == 3
    session = _spend(session, "hero")
    assert Dodge.dcv_bonus(session, "hero") == 0


def test_the_dodge_ends_at_the_next_segment_if_his_phase_was_never_spent():
    """A consumer that advances Segments without spending slots must not
    keep the bonus past the Segment the book ends it in."""
    session = _to(_session(_man("hero", spd=3)), 2)
    session, _ = Dodge.declare(session, "hero")
    session = _to(session, 8)
    assert Dodge.dcv_bonus(session, "hero") == 3
    session = _to(session, 9)
    assert Dodge.dcv_bonus(session, "hero") == 0


def test_lazer_loses_his_segment_8_phase_but_keeps_the_dodge():
    """6E2 p.24, Lazer (SPD 5: Phases 3, 5, 8, 10, 12) aborts to Dodge in
    Segment 6. When Segment 8 comes he can do nothing but still has the
    Dodge's DCV; he acts again in Segment 10."""
    session = _to(_session(_man("lazer", spd=5)), 6)
    session, evt = Dodge.declare(session, "lazer")
    assert (evt.aborted_turn, evt.aborted_segment) == (2, 8)
    assert (evt.bonus_until_turn, evt.bonus_until_segment) == (2, 10)

    session = _to(session, 8)
    assert _skip_reason(session, "lazer") == "aborted"
    assert Dodge.dcv_bonus(session, "lazer") == 3

    session = _to(session, 10)
    assert _skip_reason(session, "lazer") is None
    assert Dodge.dcv_bonus(session, "lazer") == 3   # until he takes it


def test_aborting_before_his_dex_comes_up_spends_this_segments_phase():
    """6E2 p.24: attacked in Segment 5 before his DEX came up, Lazer
    loses the Segment 5 Phase, not the next one."""
    session = _to(_session(_man("lazer", spd=5)), 5)
    session = _order(session, "lazer")
    session, evt = Dodge.declare(session, "lazer")
    assert (evt.aborted_turn, evt.aborted_segment) == (2, 5)
    assert (evt.bonus_until_turn, evt.bonus_until_segment) == (2, 8)


def test_aborting_after_he_has_acted_this_segment_spends_the_next_phase():
    session = _to(_session(_man("lazer", spd=5)), 5)
    session = _order(session, "lazer")
    session = _spend(session, "lazer")
    session, evt = Dodge.declare(session, "lazer")
    assert (evt.aborted_turn, evt.aborted_segment) == (2, 8)


def test_the_windows_wrap_into_the_next_turn():
    """SPD 2 (Phases 6, 12) aborting in Segment 7 gives up Segment 12 and
    keeps the bonus to Segment 6 of the NEXT Turn."""
    session = _to(_session(_man("hero", spd=2)), 7)
    session, evt = Dodge.declare(session, "hero")
    assert (evt.aborted_turn, evt.aborted_segment) == (2, 12)
    assert (evt.bonus_until_turn, evt.bonus_until_segment) == (3, 6)

    session = _to(session, 1, turn=3)
    assert not is_aborting(session, "hero")
    assert Dodge.dcv_bonus(session, "hero") == 3
    session = _to(session, 7, turn=3)
    assert Dodge.dcv_bonus(session, "hero") == 0


def test_a_replayed_log_expires_the_abort_at_the_same_moments():
    session = _to(_session(_man("hero", spd=4)), 4)
    session, _ = Dodge.declare(session, "hero")
    session = _to(session, 7)

    replayed = CombatSession.create(
        id="s1",
        combatants=[_man("hero", spd=4)],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    )
    for event in session.event_log:
        replayed = apply_event(replayed, event)
    assert replayed.timeline.aborts == session.timeline.aborts
    assert not is_aborting(replayed, "hero")
    assert Dodge.dcv_bonus(replayed, "hero") == 3
