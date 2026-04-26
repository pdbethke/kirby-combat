"""GM overrides — Tier 1/2/3 with audit-required justification at higher tiers.

Per Phase 2 spec Section 9 (GM tiered model):
- Tier 1: simple stat/status nudge ("set Bob's STUN to 5", "apply Stunned"
          on Carol). Mutates a Combatant snapshot field. No justification.
- Tier 2: replace/retract a single past resolved event ("re-roll", "abort
          retroactively"). Requires justification. Creates a corrective
          GMOverride event referencing the original.
- Tier 3: structural mutation (spawn/despawn a combatant, add/remove a
          surface, replace the scene). Requires justification.

This module exposes apply helpers; integration with apply_event lives in
kirby_combat/session/apply.py (extended in this task).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from kirby_combat.models import Combatant
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import GMOverride, EventAuthor, make_author_gm


def make_tier1_stun_adjust(
    session: CombatSession,
    user_id: str,
    combatant_id: str,
    new_stun: int,
    justification: str = "",
) -> GMOverride:
    """Build a Tier 1 GMOverride that sets a combatant's current STUN."""
    seq = len(session.event_log) + 1
    return GMOverride(
        id=f"{session.id}-evt-{seq}",
        session_id=session.id,
        sequence=seq,
        timestamp=datetime.now(timezone.utc),
        author=make_author_gm(user_id),
        tier=1,
        target_event_id=None,
        patch={"op": "set_current_stun", "combatant_id": combatant_id, "value": new_stun},
        justification=justification,
    )


def make_tier1_status_application(
    session: CombatSession,
    user_id: str,
    combatant_id: str,
    status: str,
    justification: str = "",
) -> GMOverride:
    seq = len(session.event_log) + 1
    return GMOverride(
        id=f"{session.id}-evt-{seq}",
        session_id=session.id,
        sequence=seq,
        timestamp=datetime.now(timezone.utc),
        author=make_author_gm(user_id),
        tier=1,
        target_event_id=None,
        patch={"op": "apply_status", "combatant_id": combatant_id, "status": status},
        justification=justification,
    )


def make_tier2_dice_override(
    session: CombatSession,
    user_id: str,
    target_event_id: str,
    new_dice_values: list[int],
    justification: str,
) -> GMOverride:
    """Tier 2: re-roll a previous event's dice. Justification REQUIRED."""
    if not justification:
        raise ValueError("Tier 2 GMOverride requires justification")
    seq = len(session.event_log) + 1
    return GMOverride(
        id=f"{session.id}-evt-{seq}",
        session_id=session.id,
        sequence=seq,
        timestamp=datetime.now(timezone.utc),
        author=make_author_gm(user_id),
        tier=2,
        target_event_id=target_event_id,
        patch={"op": "replace_dice", "values": new_dice_values},
        justification=justification,
    )


def make_tier2_retroactive_abort(
    session: CombatSession,
    user_id: str,
    target_event_id: str,
    justification: str,
) -> GMOverride:
    if not justification:
        raise ValueError("Tier 2 GMOverride requires justification")
    seq = len(session.event_log) + 1
    return GMOverride(
        id=f"{session.id}-evt-{seq}",
        session_id=session.id,
        sequence=seq,
        timestamp=datetime.now(timezone.utc),
        author=make_author_gm(user_id),
        tier=2,
        target_event_id=target_event_id,
        patch={"op": "retroactive_abort"},
        justification=justification,
    )


def make_tier3_spawn(
    session: CombatSession,
    user_id: str,
    combatant: Combatant,
    justification: str,
) -> GMOverride:
    if not justification:
        raise ValueError("Tier 3 GMOverride requires justification")
    seq = len(session.event_log) + 1
    return GMOverride(
        id=f"{session.id}-evt-{seq}",
        session_id=session.id,
        sequence=seq,
        timestamp=datetime.now(timezone.utc),
        author=make_author_gm(user_id),
        tier=3,
        target_event_id=None,
        patch={"op": "spawn_combatant", "combatant_id": combatant.id},
        justification=justification,
    )


def make_tier3_scene_mutation(
    session: CombatSession,
    user_id: str,
    scene_patch: dict[str, Any],
    justification: str,
) -> GMOverride:
    if not justification:
        raise ValueError("Tier 3 GMOverride requires justification")
    seq = len(session.event_log) + 1
    return GMOverride(
        id=f"{session.id}-evt-{seq}",
        session_id=session.id,
        sequence=seq,
        timestamp=datetime.now(timezone.utc),
        author=make_author_gm(user_id),
        tier=3,
        target_event_id=None,
        patch={"op": "mutate_scene", **scene_patch},
        justification=justification,
    )


# ---------------------------------------------------------------------------
# Apply helpers — invoked from session.apply.apply_event when a GMOverride
# is consumed. These return a new CombatSession.
# ---------------------------------------------------------------------------

def apply_tier1_override(session: CombatSession, override: GMOverride) -> CombatSession:
    """Apply a Tier 1 stat/status nudge."""
    op = override.patch.get("op")
    if op == "set_current_stun":
        cid = override.patch["combatant_id"]
        value = int(override.patch["value"])
        if cid not in session.combatants:
            raise KeyError(f"Tier 1 override: unknown combatant {cid}")
        old = session.combatants[cid]
        new = replace(old, current_stun=value)
        new_combatants = dict(session.combatants)
        new_combatants[cid] = new
        return replace(session, combatants=new_combatants)
    if op == "apply_status":
        # Status tracking lives outside the Combatant for now; this op is
        # idempotent at the structural level. Caller should follow with a
        # StatusChanged event in a richer integration.
        return session
    raise ValueError(f"unknown Tier 1 override op: {op!r}")


def apply_tier3_spawn(
    session: CombatSession,
    override: GMOverride,
    new_combatant: Combatant,
) -> CombatSession:
    """Add a combatant mid-session via a Tier 3 spawn override."""
    if override.tier != 3:
        raise ValueError("apply_tier3_spawn requires a Tier 3 GMOverride")
    new_combatants = dict(session.combatants)
    new_combatants[new_combatant.id] = new_combatant
    return replace(session, combatants=new_combatants)


def apply_tier3_despawn(session: CombatSession, combatant_id: str) -> CombatSession:
    """Remove a combatant mid-session."""
    new_combatants = dict(session.combatants)
    new_combatants.pop(combatant_id, None)
    return replace(session, combatants=new_combatants)
