"""Session-aware wrapper around the pure attack resolver.

``AttackAction.resolve`` (and the ``resolve_attack`` dispatcher in
``actions/__init__.py``) is a pure calculator: a total function of its
inputs with no session coupling, which is exactly what makes it trivial
to test and safe to call from anywhere. That purity is an asset and is
left untouched here.

The gap it leaves is that nothing ever records the outcome anywhere —
callers that DO have a session (and want the attack's effects on the
event log) had no session-aware entry point to call, so kirby-api grew
its own ``ActionResolved`` construction instead
(``llm_driver.py:_emit_resolution``). This module adds that entry point
inside kirby-combat, following the same shape already used by
``Flash.apply`` (``actions/flash.py``) and ``Grab.declare_and_resolve``
(``actions/grab.py``): run the pure calculation, then emit the event(s)
that describe it.

This lives in its own module (rather than being folded into
``actions/base.py``) because it is a different kind of thing from the
pipeline in that file: ``base.py`` holds pure, session-free resolution
logic shared by the concrete attack action classes, while this module is
glue between that pure core and the event-sourced ``CombatSession``. Its
only reason to import ``CombatSession``/``apply_event``/``ActionResolved``
at all is to record — mixing that into ``base.py`` would put session
plumbing in the one place the brief explicitly wants kept pure.

Opt-in only: existing callers of ``resolve_attack`` / ``AttackAction.resolve``
are completely unaffected — nothing here changes their behaviour, and
nothing here emits anything on their behalf. A caller must choose to call
``resolve_attack_in_session`` instead, which is what keeps this from
double-logging against kirby-api's own emission.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from kirby_combat.actions import resolve_attack
from kirby_combat.models import AttackInput, AttackResult
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_combatant,
)
from kirby_combat.template import CombatTemplate


def resolve_attack_in_session(
    session: CombatSession,
    attack: AttackInput,
    template: CombatTemplate,
    *,
    declaration_event_id: str | None = None,
    action_type: str = "attack",
) -> tuple[CombatSession, AttackResult]:
    """Resolve an attack and record the outcome on the session's event log.

    Runs the pure ``resolve_attack`` calculation unchanged, then emits an
    ``ActionResolved`` carrying the outcome — most importantly
    ``status_changes``, which the pure resolver computes
    (``AttackAction.resolve``, via ``determine_status_changes``) but has no
    session to hand it to, so today it is discarded by every caller that
    doesn't hand-roll its own recording.

    If ``declaration_event_id`` is omitted, an ``ActionDeclared`` is emitted
    first (mirroring ``Flash.apply`` / ``Grab.declare_and_resolve``) and its
    id is used as the resolution's ``declaration_event_id``. Pass an existing
    id when the caller already declared the action itself.

    Returns ``(new_session, result)`` — ``result`` is exactly what
    ``resolve_attack`` returned; nothing about the pure result is altered.
    """
    from kirby_combat.session.apply import apply_event

    result = resolve_attack(attack, template)

    attacker_id = attack.attacker.id
    target_id = attack.target.id
    now = datetime.now(timezone.utc)

    s = session
    decl_id = declaration_event_id
    if decl_id is None:
        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=s.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id,
            action_type=action_type,
            targets=[target_id],
            parameters={"power_xmlid": attack.power.xmlid},
        )
        s = apply_event(s, declared)
        decl_id = declared.id

    # Established payload keys, matched to what kirby-api's own
    # _emit_resolution-style construction already writes (llm_driver.py
    # reads "hit" at situation_builder.py:690 / soliloquy.py:256-258,
    # "stun_dealt" at soliloquy.py:139,260, "body_dealt" at
    # soliloquy.py:140,263). "status_changes" is new: nothing persists it
    # today even though llm_driver.py checks `result.status_changes` for
    # "Stunned" in six places (2757, 6215, 7997, 8176, 9861, 9938) —
    # re-deriving it every request because it was never recorded. "Knocked
    # Out" is one of the strings `determine_status_changes` may return
    # (kirby_combat/resolution/status.py), so it is already carried inside
    # status_changes rather than duplicated as a separate boolean key.
    result_payload: dict[str, Any] = {
        "hit": result.hit,
        "stun_dealt": result.stun_dealt,
        "body_dealt": result.body_dealt,
        "status_changes": list(result.status_changes),
        "power_xmlid": result.power_xmlid,
        "target_id": target_id,
    }

    resolved = ActionResolved(
        id=str(uuid.uuid4()),
        session_id=s.id,
        sequence=len(s.event_log) + 1,
        timestamp=now,
        author=make_author_combatant(attacker_id),
        declaration_event_id=decl_id,
        result_payload=result_payload,
    )
    s = apply_event(s, resolved)

    return s, result


__all__ = ["resolve_attack_in_session"]
