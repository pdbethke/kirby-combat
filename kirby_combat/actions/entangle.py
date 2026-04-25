"""Entangle attack — applies an entanglement; victims escape via STR.

HERO 6E1 pg 218-220:
- Entangle creates a temporary obstruction with its own BODY, PD, ED
- Target inside the entangle has -2 OCV and -2 DCV
- Casual STR escape (half-phase): BODY damage = STR/10 minus entangle PD
- Full STR escape (full-phase): BODY damage = STR/5 minus entangle PD
- Once entangle BODY ≤ 0, target is free

State tracking: scan event log for EntangleApplied / EntangleEscape pairs.
No Combatant model changes; no apply.py extensions in this task.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, EntangleApplied, EntangleEscape,
    make_author_combatant,
)


@dataclass(frozen=True)
class EntangleResult:
    target_id: str
    method: str                          # "applied" | "casual_str" | "full_str"
    damage_to_entangle_body: int
    body_remaining: int
    escaped: bool


class Entangle:
    name: str = "entangle"

    # ------------------------------------------------------------------ apply
    @staticmethod
    def apply(
        session: CombatSession,
        *,
        attacker_id: str,
        target_id: str,
        entangle_body: int,
        entangle_pd: int,
        entangle_ed: int,
    ) -> tuple[CombatSession, EntangleResult]:
        """Apply an entangle to target. Emits ActionDeclared + ActionResolved + EntangleApplied."""
        from kirby_combat.session.apply import apply_event

        now = datetime.now(timezone.utc)

        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id,
            action_type="entangle",
            targets=[target_id],
            parameters={
                "entangle_body": entangle_body,
                "entangle_pd": entangle_pd,
                "entangle_ed": entangle_ed,
            },
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
                "type": "entangle_attack",
                "success": True,
                "target_id": target_id,
            },
        )
        s = apply_event(s, resolved)

        applied = EntangleApplied(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            target_id=target_id,
            entangle_body=entangle_body,
            entangle_pd=entangle_pd,
            entangle_ed=entangle_ed,
        )
        s = apply_event(s, applied)

        return s, EntangleResult(
            target_id=target_id,
            method="applied",
            damage_to_entangle_body=0,
            body_remaining=entangle_body,
            escaped=False,
        )

    # ------------------------------------------------------------------ escape_attempt
    @staticmethod
    def escape_attempt(
        session: CombatSession,
        *,
        target_id: str,
        str_used: int,
        escape_type: str,
    ) -> tuple[CombatSession, EntangleResult]:
        """Attempt to escape an entangle.

        escape_type: "casual" (half-phase, STR/10) or "full" (full-phase, STR/5).
        Damage to entangle body = (raw_dice) − entangle_pd, clamped at 0.
        """
        from kirby_combat.session.apply import apply_event

        if escape_type not in ("casual", "full"):
            raise ValueError(f"unknown escape_type: {escape_type!r}")

        is_e, current_body = Entangle.is_entangled(session, target_id)
        if not is_e:
            raise ValueError(f"{target_id} is not entangled; cannot escape")

        # Find the most recent EntangleApplied for this target to get pd
        entangle_pd = 0
        for evt in reversed(session.event_log):
            if evt.kind == "EntangleApplied" and getattr(evt, "target_id", None) == target_id:
                entangle_pd = evt.entangle_pd
                break

        raw = str_used // 10 if escape_type == "casual" else str_used // 5
        damage = max(0, raw - entangle_pd)

        body_remaining = max(0, (current_body or 0) - damage)
        escaped = body_remaining <= 0
        method = "casual_str" if escape_type == "casual" else "full_str"

        evt = EntangleEscape(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(target_id),
            target_id=target_id,
            method=method,
            damage_to_entangle_body=damage,
            escaped=escaped,
        )
        s = apply_event(session, evt)

        return s, EntangleResult(
            target_id=target_id,
            method=method,
            damage_to_entangle_body=damage,
            body_remaining=body_remaining,
            escaped=escaped,
        )

    # ------------------------------------------------------------------ is_entangled
    @staticmethod
    def is_entangled(
        session: CombatSession, combatant_id: str,
    ) -> tuple[bool, Optional[int]]:
        """Walk event log accumulating entangle body for combatant_id.

        Returns (True, body_remaining) when entangled; (False, None) when not.
        """
        body: Optional[int] = None
        for evt in session.event_log:
            kind = evt.kind
            if kind == "EntangleApplied" and getattr(evt, "target_id", None) == combatant_id:
                body = evt.entangle_body
            elif kind == "EntangleEscape" and getattr(evt, "target_id", None) == combatant_id:
                if body is None:
                    continue        # escape with no prior entangle (shouldn't happen)
                if evt.escaped:
                    body = None
                else:
                    body = max(0, body - evt.damage_to_entangle_body)
                    if body == 0:
                        body = None
        return (body is not None, body)

    # ------------------------------------------------------------------ modifiers
    @staticmethod
    def modifiers(
        session: CombatSession, combatant_id: str,
    ) -> dict:
        """Return OCV/DCV penalties while entangled; empty dict otherwise."""
        is_e, _ = Entangle.is_entangled(session, combatant_id)
        return {"ocv_modifier": -2, "dcv_modifier": -2} if is_e else {}
