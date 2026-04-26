"""Rewind — per-action truncation + replay."""
from datetime import datetime, timezone

from kirby_combat.session import CombatSession, apply_event, rewind_to_sequence
from kirby_combat.session.events import SegmentAdvanced, make_author_engine
from kirby_combat.models import Combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller


def _session() -> CombatSession:
    c = Combatant(
        id="a", name="a", ocv=8, dcv=8, omcv=5, dmcv=5,
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


def test_rewind_truncates_events_after_target():
    s = _session()
    s = apply_event(s, SegmentAdvanced(
        id="e2", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=12, to_segment=1, to_turn=2,
    ))
    s = apply_event(s, SegmentAdvanced(
        id="e3", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=1, to_segment=2, to_turn=2,
    ))
    assert len(s.event_log) == 3
    assert s.timeline.segment == 2
    s2 = rewind_to_sequence(s, target_sequence=2)
    assert len(s2.event_log) == 2
    assert s2.timeline.segment == 1


def test_rewind_to_zero_empties_log_and_resets_snapshot():
    s = _session()
    s = apply_event(s, SegmentAdvanced(
        id="e2", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=12, to_segment=1, to_turn=2,
    ))
    s2 = rewind_to_sequence(s, target_sequence=0)
    assert s2.event_log == []
    assert s2.status == "setup"
    assert s2.timeline.segment == 12


def test_rewind_past_end_is_noop():
    s = _session()
    s2 = rewind_to_sequence(s, target_sequence=999)
    assert len(s2.event_log) == len(s.event_log)
    assert s2.timeline.segment == s.timeline.segment
