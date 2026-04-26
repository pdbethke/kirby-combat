"""CombatEvent union type tests."""
from datetime import datetime, timezone
import pytest

from kirby_combat.session.events import (
    EventAuthor,
    SessionStarted,
    SegmentAdvanced,
    ActionDeclared,
    ActionResolved,
    RecoveryTaken,
    MovementResolved,
    StatusChanged,
    AbortDeclared,
    HeldActionDeclared,
    HeldActionReleased,
    AdjustmentApplied,
    AdjustmentFaded,
    EntangleApplied,
    EntangleEscape,
    FlashApplied,
    FlashRecovered,
    EnvironmentalTriggered,
    GMOverride,
    SessionEnded,
    make_author_combatant,
    make_author_gm,
    make_author_engine,
)


def test_author_combatant_shape():
    a = make_author_combatant("alice")
    assert a.type == "combatant"
    assert a.id == "alice"


def test_author_gm_shape():
    a = make_author_gm("user-uuid-123")
    assert a.type == "gm"
    assert a.id == "user-uuid-123"


def test_author_engine_shape():
    a = make_author_engine()
    assert a.type == "engine"
    assert a.id == "engine"


def test_session_started_required_fields():
    e = SessionStarted(
        id="evt-1",
        session_id="sess-1",
        sequence=1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_engine(),
        scene_id="scene-1",
        combatant_ids=["alice", "bob"],
    )
    assert e.sequence == 1
    assert e.scene_id == "scene-1"


def test_action_declared_references_combatant():
    e = ActionDeclared(
        id="evt-2",
        session_id="sess-1",
        sequence=2,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant("alice"),
        combatant_id="alice",
        action_type="strike",
        targets=["bob"],
        parameters={"aim": None},
    )
    assert e.combatant_id == "alice"
    assert e.targets == ["bob"]


def test_action_resolved_references_declaration():
    e = ActionResolved(
        id="evt-3",
        session_id="sess-1",
        sequence=3,
        timestamp=datetime.now(timezone.utc),
        author=make_author_engine(),
        declaration_event_id="evt-2",
        result_payload={"hit": True, "stun_dealt": 12, "body_dealt": 2},
    )
    assert e.declaration_event_id == "evt-2"
    assert e.result_payload["hit"] is True


def test_gm_override_tier_and_justification():
    e = GMOverride(
        id="evt-99",
        session_id="sess-1",
        sequence=99,
        timestamp=datetime.now(timezone.utc),
        author=make_author_gm("gm-user-1"),
        tier=2,
        target_event_id="evt-3",
        patch={"new_dice": [1, 2, 3]},
        justification="Rolled wrong dice type, fixing.",
    )
    assert e.tier == 2
    assert e.justification.startswith("Rolled")


def test_gm_override_tier_out_of_range_raises():
    with pytest.raises(ValueError):
        GMOverride(
            id="evt-100",
            session_id="sess-1",
            sequence=100,
            timestamp=datetime.now(timezone.utc),
            author=make_author_gm("gm-user-1"),
            tier=5,  # invalid
            target_event_id=None,
            patch={},
            justification="x",
        )
