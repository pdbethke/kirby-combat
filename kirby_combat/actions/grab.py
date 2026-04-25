"""Grab — opposed-STR contest; grabbed status tracked via event log scan.

HERO 6E2 pg 67-68:
- Half-phase action; assumes the to-hit attack already landed
- Deterministic STR contest: attacker_str > target_str → success; defender wins ties
- Successful grab tags the victim as "grabbed by attacker_id"
- Escape: opposed STR on victim's phase; escaper wins only if escaper_str > grabber_str
  (grabber wins ties)

This module tracks grab state by scanning ActionResolved events whose
result_payload has type in {"grab", "grab_escape"}.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_combatant,
)


@dataclass
class GrabResult:
    success: bool
    attacker_id: str
    target_id: str
    attacker_str: int
    target_str: int


class Grab:
    name: str = "grab"

    # ------------------------------------------------------------------ declare
    @staticmethod
    def declare_and_resolve(
        session: CombatSession,
        *,
        attacker_id: str,
        target_id: str,
        attacker_str: int,
        target_str: int,
    ) -> tuple[CombatSession, GrabResult]:
        """Apply a grab attempt. Emits ActionDeclared + ActionResolved events.

        Returns (new_session, result). The grab succeeds iff
        attacker_str > target_str (defender wins ties).
        """
        from kirby_combat.session.apply import apply_event

        success = attacker_str > target_str
        result = GrabResult(
            success=success,
            attacker_id=attacker_id, target_id=target_id,
            attacker_str=attacker_str, target_str=target_str,
        )

        now = datetime.now(timezone.utc)
        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id,
            action_type="grab",
            targets=[target_id],
            parameters={"attacker_str": attacker_str, "target_str": target_str},
        )
        s = apply_event(session, declared)

        resolved = ActionResolved(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            declaration_event_id=declared.id,
            result_payload={
                "type": "grab",
                "success": success,
                "attacker_id": attacker_id,
                "target_id": target_id,
                "attacker_str": attacker_str,
                "target_str": target_str,
            },
        )
        s = apply_event(s, resolved)
        return s, result

    # ------------------------------------------------------------------ escape
    @staticmethod
    def escape(
        session: CombatSession,
        *,
        escaper_id: str,
        escaper_str: int,
        grabber_str: int,
    ) -> tuple[CombatSession, GrabResult]:
        """Attempt to escape a grab. Emits action_type="grab_escape" events.

        Raises ValueError if escaper isn't currently grabbed. Escaper wins iff
        escaper_str > grabber_str (grabber wins ties).
        """
        from kirby_combat.session.apply import apply_event

        is_g, grabber_id = Grab.is_grabbed(session, escaper_id)
        if not is_g:
            raise ValueError(f"{escaper_id} is not grabbed; cannot escape")

        success = escaper_str > grabber_str
        result = GrabResult(
            success=success,
            attacker_id=grabber_id or "",
            target_id=escaper_id,
            attacker_str=grabber_str,
            target_str=escaper_str,
        )

        now = datetime.now(timezone.utc)
        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(escaper_id),
            combatant_id=escaper_id,
            action_type="grab_escape",
            targets=[grabber_id or ""],
            parameters={"escaper_str": escaper_str, "grabber_str": grabber_str},
        )
        s = apply_event(session, declared)

        resolved = ActionResolved(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(escaper_id),
            declaration_event_id=declared.id,
            result_payload={
                "type": "grab_escape",
                "success": success,
                "escaper_id": escaper_id,
                "grabber_id": grabber_id,
                "escaper_str": escaper_str,
                "grabber_str": grabber_str,
            },
        )
        s = apply_event(s, resolved)
        return s, result

    # ------------------------------------------------------------------ is_grabbed
    @staticmethod
    def is_grabbed(
        session: CombatSession, combatant_id: str,
    ) -> tuple[bool, Optional[str]]:
        """Scan the event log for the most recent grab/escape pair affecting
        this combatant. Returns (True, grabber_id) if currently grabbed,
        (False, None) otherwise.
        """
        grabber: Optional[str] = None
        for evt in session.event_log:
            if evt.kind != "ActionResolved":
                continue
            payload = getattr(evt, "result_payload", None) or {}
            ptype = payload.get("type")
            if (
                ptype == "grab"
                and payload.get("target_id") == combatant_id
                and payload.get("success") is True
            ):
                grabber = payload.get("attacker_id")
            elif (
                ptype == "grab_escape"
                and payload.get("escaper_id") == combatant_id
                and payload.get("success") is True
            ):
                grabber = None
        return (grabber is not None, grabber)
