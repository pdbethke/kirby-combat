"""Spawn / despawn combatants mid-session via Tier 3 GMOverride.

Higher-level helpers that emit a GMOverride event AND return the new
session state with the combatants dict mutated.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from kirby_combat.models import StatBlockCombatant
from kirby_combat.scene.scene import Position, Scene
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import GMOverride, make_author_gm
from kirby_combat.gm.overrides import (
    make_tier3_spawn, apply_tier3_spawn, apply_tier3_despawn,
)


def spawn_combatant(
    session: CombatSession,
    user_id: str,
    new_combatant: StatBlockCombatant,
    position: Position | None = None,
    justification: str = "GM spawn",
) -> tuple[CombatSession, GMOverride]:
    """Add a combatant to the session, optionally placing them in the scene.

    Returns (new_session, override_event). The override is appended to the
    event log via apply_event when the caller passes it through.
    """
    if not justification:
        raise ValueError("Tier 3 GMOverride requires justification")
    override = make_tier3_spawn(session, user_id, new_combatant, justification)
    new_session = apply_tier3_spawn(session, override, new_combatant)
    if position is not None and isinstance(new_session.scene, Scene):
        new_scene = new_session.scene.place_combatant(new_combatant.id, position)
        new_session = replace(new_session, scene=new_scene)
    return new_session, override


def despawn_combatant(
    session: CombatSession,
    user_id: str,
    combatant_id: str,
    justification: str = "GM despawn",
) -> tuple[CombatSession, GMOverride]:
    if not justification:
        raise ValueError("Tier 3 GMOverride requires justification")
    seq = len(session.event_log) + 1
    override = GMOverride(
        id=f"{session.id}-evt-{seq}",
        session_id=session.id,
        sequence=seq,
        timestamp=datetime.now(timezone.utc),
        author=make_author_gm(user_id),
        tier=3,
        target_event_id=None,
        patch={"op": "despawn_combatant", "combatant_id": combatant_id},
        justification=justification,
    )
    new_session = apply_tier3_despawn(session, combatant_id)
    return new_session, override


def is_active_target(session: CombatSession, combatant_id: str) -> bool:
    """A combatant is a valid action target only if they're in session.combatants."""
    return combatant_id in session.combatants


def spawn_skips_immediate_segment(
    spawned_in_segment: int,
    spawned_combatant_segments: list[int],
) -> bool:
    """Per Phase 2 spec: a combatant spawned mid-segment does NOT act
    immediately in that segment; they wait for their next phase.
    """
    return spawned_in_segment in spawned_combatant_segments
