"""Brace — 1/2 DCV, 1/2 range penalty on next ranged attack (6E2 pg 64)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import ActionDeclared, ActionResolved, make_author_combatant

_RANGE_PENALTY_FACTOR = 0.5
_DCV_FACTOR = 0.5


class Brace:
    """Brace tactical modifier.

    The combatant braces to negate recoil/movement effects on a ranged attack:
    - Range penalty is halved (range_penalty_factor = 0.5).
    - DCV is halved (dcv_factor = 0.5) while bracing.
    """

    name: str = "brace"

    @staticmethod
    def declare(
        session: CombatSession,
        combatant_id: str,
    ) -> tuple[CombatSession, ActionDeclared]:
        """Record a Brace declaration.

        Emits ActionDeclared(action_type="brace").
        """
        from kirby_combat.session.apply import apply_event

        evt = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(combatant_id),
            combatant_id=combatant_id,
            action_type="brace",
            targets=[],
            parameters={},
        )
        return apply_event(session, evt), evt

    @staticmethod
    def modifiers_for_pending_attack(
        session: CombatSession, combatant_id: str
    ) -> dict[str, Any]:
        """Return brace modifiers if pending, else {}.

        Returns:
            {"range_penalty_factor": 0.5, "dcv_factor": 0.5} when active,
            {} when no brace has been declared or it has already resolved.
        """
        declaration_id: str | None = None
        for evt in reversed(session.event_log):
            if (
                isinstance(evt, ActionDeclared)
                and evt.combatant_id == combatant_id
                and evt.action_type == "brace"
            ):
                declaration_id = evt.id
                break

        if declaration_id is None:
            return {}

        # Check if already resolved.
        for evt in session.event_log:
            if (
                isinstance(evt, ActionResolved)
                and evt.declaration_event_id == declaration_id
            ):
                return {}

        return {
            "range_penalty_factor": _RANGE_PENALTY_FACTOR,
            "dcv_factor": _DCV_FACTOR,
        }
