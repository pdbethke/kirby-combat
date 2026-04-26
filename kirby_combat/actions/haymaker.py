"""Haymaker — +4 DC on next attack, -5 DCV until resolved (6E2 pg 73)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import ActionDeclared, ActionResolved, make_author_combatant

_DC_BONUS = 4
_DCV_DELTA = -5


class Haymaker:
    """Haymaker tactical modifier.

    Declare before the attack phase. The haymaker resolves 1 segment later,
    granting +4 DC while imposing -5 DCV on the attacker until resolved.
    """

    name: str = "haymaker"

    @staticmethod
    def declare(
        session: CombatSession,
        combatant_id: str,
        *,
        planned_attack_action_type: str = "strike",
    ) -> tuple[CombatSession, ActionDeclared]:
        """Record a haymaker declaration.

        Emits ActionDeclared(action_type="haymaker") with
        parameters={"planned_attack_action_type": ...}.
        """
        from kirby_combat.session.apply import apply_event

        evt = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(combatant_id),
            combatant_id=combatant_id,
            action_type="haymaker",
            targets=[],
            parameters={"planned_attack_action_type": planned_attack_action_type},
        )
        return apply_event(session, evt), evt

    @staticmethod
    def modifiers_for_pending_attack(
        session: CombatSession, combatant_id: str
    ) -> dict[str, Any]:
        """Return {dc_bonus: 4, dcv_delta: -5} if a haymaker is pending, else {}.

        "Pending" means the most recent haymaker declaration for this combatant
        has no corresponding ActionResolved referencing its id.
        """
        declaration_id: str | None = None
        for evt in reversed(session.event_log):
            if (
                isinstance(evt, ActionDeclared)
                and evt.combatant_id == combatant_id
                and evt.action_type == "haymaker"
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

        return {"dc_bonus": _DC_BONUS, "dcv_delta": _DCV_DELTA}
