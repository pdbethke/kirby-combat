"""Session-recording wrappers for the mental powers.

WHY THESE DID NOT EXIST. ``mental/mind_control.py``, ``mental_illusion.py``
and ``telepathy.py`` have held correct, tested resolvers for a long time ---
and nothing in production ever called them. The parked kirby-api driver
wrote its own version of each inside its 1,070-line dispatcher, so the
engine's copies were reachable only from their own unit tests.

The measurement that makes the point (2026-09-06): the engine states the
mental Attack Roll once, in ``mental_combat.py`` --- "Target number = 11 +
attacker.omcv - target.dmcv + modifiers". The parked driver writes that
same expression out at four separate lines: 8619, 9592, 9706 and 11172.

**Nothing caught it because every one of those suites is green.** The
engine's rules are correct and tested; what was missing is a caller. No
test asserts "something reaches this", which is exactly the shape of defect
the resolver registry now makes countable --- ``registered_kinds()`` moving
is the assertion that was never there.

WHAT THESE ADD, AND WHAT THEY DELIBERATELY DO NOT. Each wrapper runs the
pure resolver UNCHANGED and records an ``ActionResolved`` carrying its
outcome, exactly as ``resolve_mental_blast_in_session`` does. None of them
re-derives a rule, and none applies an effect to combatant state: Mind
Control, Mental Illusion and Telepathy produce a DEGREE against EGO rather
than damage, and the persistent consequences of a degree (a puppet acting
against its allies, an illusion believed) are effect-state, which follows
the house pattern in ``session/effects.py`` and is not smuggled in here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from kirby_combat.mental.mental_illusion import resolve_mental_illusion
from kirby_combat.mental.mind_control import resolve_mind_control
from kirby_combat.mental.telepathy import resolve_telepathy
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_combatant,
)

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


def _declare(
    session: "CombatSession", attacker_id: str, target_id: str,
    action_type: str, declaration_event_id: str | None, now: datetime,
) -> tuple["CombatSession", str]:
    """Emit an ``ActionDeclared`` unless the caller already declared one."""
    if declaration_event_id is not None:
        return session, declaration_event_id
    declared = ActionDeclared(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=now,
        author=make_author_combatant(attacker_id),
        combatant_id=attacker_id,
        action_type=action_type,
        targets=[target_id],
        parameters={},
    )
    return apply_event(session, declared), declared.id


def _record(
    session: "CombatSession", attacker_id: str, decl_id: str,
    payload: dict[str, Any], now: datetime,
) -> "CombatSession":
    resolved = ActionResolved(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=now,
        author=make_author_combatant(attacker_id),
        declaration_event_id=decl_id,
        result_payload=payload,
    )
    return apply_event(session, resolved)


def resolve_mind_control_in_session(
    session: "CombatSession", attacker, target, effect_dice_values: list[int],
    *, declaration_event_id: str | None = None, action_type: str = "mind_control",
):
    """Resolve Mind Control and record the degree achieved.

    The pure resolver classifies the effect roll against the target's EGO on
    the degree ladder (ego_push / simple / contrary / violent). That degree
    is what the payload carries: it is the whole outcome, since Mind Control
    deals no STUN and no BODY.
    """
    now = datetime.now(timezone.utc)
    result = resolve_mind_control(attacker, target, effect_dice_values)
    s, decl_id = _declare(
        session, attacker.id, target.id, action_type, declaration_event_id, now,
    )
    s = _record(s, attacker.id, decl_id, {
        "kind": action_type,
        "target_id": target.id,
        "effect_total": result.effect_total,
        "degree": result.degree,
        "target_ego": result.target_ego,
    }, now)
    return s, result


def resolve_mental_illusion_in_session(
    session: "CombatSession", attacker, target, effect_dice_values: list[int],
    *, declaration_event_id: str | None = None, action_type: str = "mental_illusion",
):
    """Resolve a Mental Illusion and record the degree achieved."""
    now = datetime.now(timezone.utc)
    result = resolve_mental_illusion(attacker, target, effect_dice_values)
    s, decl_id = _declare(
        session, attacker.id, target.id, action_type, declaration_event_id, now,
    )
    s = _record(s, attacker.id, decl_id, {
        "kind": action_type,
        "target_id": target.id,
        "effect_total": result.effect_total,
        "degree": result.degree,
        "target_ego": result.target_ego,
    }, now)
    return s, result


def resolve_telepathy_in_session(
    session: "CombatSession", attacker, target, effect_dice_values: list[int],
    *, target_has_mental_awareness: bool = False,
    declaration_event_id: str | None = None, action_type: str = "telepathy",
):
    """Resolve Telepathy and record what was read.

    ``target_has_mental_awareness`` is passed through unchanged --- whether
    the target notices is the pure resolver's call, not this wrapper's.
    """
    now = datetime.now(timezone.utc)
    result = resolve_telepathy(
        attacker, target, effect_dice_values,
        target_has_mental_awareness=target_has_mental_awareness,
    )
    s, decl_id = _declare(
        session, attacker.id, target.id, action_type, declaration_event_id, now,
    )
    s = _record(s, attacker.id, decl_id, {
        "kind": action_type,
        "target_id": target.id,
        "effect_total": result.effect_total,
        "degree": result.degree,
        "target_ego": result.target_ego,
        "target_is_aware": result.target_is_aware,
    }, now)
    return s, result
