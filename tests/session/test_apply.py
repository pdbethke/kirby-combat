"""apply_event dispatcher tests — total function over the event union."""
from datetime import datetime, timezone
import pytest

from dataclasses import replace

from kirby_combat.session import CombatSession, apply_event
from kirby_combat.session.events import (
    SegmentAdvanced, make_author_engine,
    ActionDeclared, make_author_combatant,
)
from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller
from kirby_combat.session.timeline import ActingSlot, ActionIntent
from kirby_combat.talents.lightning_reflexes import LightningReflexesGrant


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


def _session_with_lightning_reflexes_slot(*, option_id: str, option_alias: str = "strike"):
    """A session whose timeline already carries a *resolved* ActingSlot for
    "alice" (segment == the session's current segment, 12) electing
    Lightning Reflexes for "strike" -- the shape a driver that ran
    resolve_acting_order and stored the result would produce. See
    apply.py's `_enforce_lightning_reflexes_phase_restriction` docstring
    for why nothing in this codebase writes that shape today."""
    s = _session()
    slot = ActingSlot(
        combatant_id="alice",
        segment=s.timeline.segment,
        dex_at_phase=20,
        int_tiebreak=15,
        pre_tiebreak=15,
        ego=15,
        intent=ActionIntent("strike", elect_lightning_reflexes=True),
        lightning_reflexes_grants=(
            LightningReflexesGrant(
                levels=4, option_id=option_id, option_alias=option_alias),
        ),
    )
    return replace(s, timeline=replace(s.timeline, acting_order=[slot]))


def _declare(s: CombatSession, action_type: str) -> ActionDeclared:
    return ActionDeclared(
        id="evt-2", session_id="s1", sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant("alice"),
        combatant_id="alice", action_type=action_type, targets=[], parameters={},
    )


def test_electing_lightning_reflexes_forbids_a_different_declared_action():
    """6E1 p.116(c): "no movement, acrobatics, or other Actions" in the
    Phase where the elected bonus is used. Integration-level: this goes
    through apply_event, not phase_restricted_to directly, so it proves
    the restriction is actually enforced and not merely advisory."""
    s = _session_with_lightning_reflexes_slot(option_id="SINGLE")
    with pytest.raises(ValueError, match="Lightning Reflexes"):
        apply_event(s, _declare(s, "move"))


def test_electing_lightning_reflexes_permits_the_elected_action():
    s = _session_with_lightning_reflexes_slot(option_id="SINGLE")
    s2 = apply_event(s, _declare(s, "strike"))
    assert s2.event_log[-1].kind == "ActionDeclared"


def test_all_scope_election_does_not_restrict_the_phase():
    """An ALL-scope grant covers every Action, so electing it is not
    meaningfully restricted (6E1 p.116(c)) -- a different declared action
    must go through."""
    s = _session_with_lightning_reflexes_slot(
        option_id="ALL", option_alias="All Actions")
    s2 = apply_event(s, _declare(s, "move"))
    assert s2.event_log[-1].kind == "ActionDeclared"


def test_apply_unknown_event_raises():
    s = _session()

    class WeirdEvent:
        kind = "Unknown"
        sequence = len(s.event_log) + 1
        session_id = "s1"

    with pytest.raises(TypeError, match="unhandled event"):
        apply_event(s, WeirdEvent())  # type: ignore[arg-type]
