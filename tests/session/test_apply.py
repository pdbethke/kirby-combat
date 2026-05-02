"""apply_event dispatcher tests — total function over the event union."""
from datetime import datetime, timezone
import pytest

from kirby_combat.session import CombatSession, apply_event
from kirby_combat.session.events import (
    SegmentAdvanced, make_author_engine,
    ActionDeclared, make_author_combatant,
)
from fixtures.synthetic_hero import synthetic_combatant as Combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller


def _session() -> CombatSession:
    c = Combatant(
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


def test_apply_segment_advanced_updates_timeline():
    s = _session()
    evt = SegmentAdvanced(
        id="evt-x", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=12, to_segment=1, to_turn=2,
    )
    s2 = apply_event(s, evt)
    assert s2.timeline.segment == 1
    assert s2.timeline.turn == 2
    assert evt in s2.event_log


def test_apply_sequence_must_be_next():
    s = _session()
    evt = SegmentAdvanced(
        id="evt-x", session_id="s1", sequence=5,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        from_segment=12, to_segment=1, to_turn=2,
    )
    with pytest.raises(ValueError, match="sequence"):
        apply_event(s, evt)


def test_apply_action_declared_does_not_mutate_combatants():
    s = _session()
    declared = ActionDeclared(
        id="evt-2", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant("alice"),
        combatant_id="alice", action_type="strike", targets=[], parameters={},
    )
    s2 = apply_event(s, declared)
    assert s2.combatants["alice"].current_stun == 30
    assert s2.event_log[-1].kind == "ActionDeclared"


def test_apply_unknown_event_raises():
    s = _session()

    class WeirdEvent:
        kind = "Unknown"
        sequence = len(s.event_log) + 1
        session_id = "s1"

    with pytest.raises(TypeError, match="unhandled event"):
        apply_event(s, WeirdEvent())  # type: ignore[arg-type]
