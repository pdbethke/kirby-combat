"""Spawn / despawn — combatants added or removed mid-session via Tier 3."""
import pytest

from kirby_combat.gm.spawn_despawn import (
    spawn_combatant, despawn_combatant,
    is_active_target, spawn_skips_immediate_segment,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_combat.scene.scene import Position, Scene, SceneBounds, AmbientConditions
from tests.fixtures.synthetic_hero import synthetic_combatant


def _ct(id_: str):
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=3, dmcv=3,
        spd=4, dex=15, ego=10, str_=15, con=15, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _scene() -> Scene:
    return Scene(
        id="sc", name="x",
        bounds=SceneBounds(0, 0, 0, 100, 100, 50),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )


def _session(with_scene: bool = False) -> CombatSession:
    return CombatSession.create(
        id="s1", combatants=[_ct("alice")],
        scene=_scene() if with_scene else None,
        template=CombatTemplate.default_6e_superheroic(),
    )


def test_spawn_adds_combatant_mid_session():
    s = _session()
    s2, ev = spawn_combatant(s, "gm-pete", _ct("bob"), justification="ambush")
    assert "bob" in s2.combatants


def test_spawn_places_combatant_in_scene_at_given_position():
    s = _session(with_scene=True)
    s2, ev = spawn_combatant(
        s, "gm-pete", _ct("bob"),
        position=Position(10, 10, 0),
        justification="ambush",
    )
    assert "bob" in s2.scene.combatant_positions
    assert s2.scene.combatant_positions["bob"].x == 10


def test_spawn_emits_gmoverride_tier_3_event():
    s = _session()
    _, ev = spawn_combatant(s, "gm-pete", _ct("bob"), justification="ambush")
    assert ev.tier == 3
    assert ev.patch["op"] == "spawn_combatant"


def test_despawn_removes_combatant_from_snapshot_and_timeline():
    s = _session()
    s2, ev = spawn_combatant(s, "gm-pete", _ct("bob"), justification="ambush")
    s3, ev2 = despawn_combatant(s2, "gm-pete", "bob", justification="defeated")
    assert "bob" not in s3.combatants
    assert ev2.tier == 3
    assert ev2.patch["op"] == "despawn_combatant"


def test_despawned_combatant_cannot_be_target_of_future_actions():
    s = _session()
    s2, _ = spawn_combatant(s, "gm-pete", _ct("bob"), justification="ambush")
    s3, _ = despawn_combatant(s2, "gm-pete", "bob", justification="gone")
    assert is_active_target(s3, "bob") is False
    assert is_active_target(s3, "alice") is True


def test_spawn_into_active_segment_does_not_get_immediate_phase():
    # If spawned in a segment they would normally act in, the spec says no
    # immediate phase. This helper just classifies whether the segment is
    # "their" segment; the timeline integration uses this to skip them.
    spawned_segments = [3, 6, 9, 12]   # SPD 4
    # Spawning in segment 3 — would normally act, but we skip this segment.
    assert spawn_skips_immediate_segment(3, spawned_segments) is True
    assert spawn_skips_immediate_segment(4, spawned_segments) is False
