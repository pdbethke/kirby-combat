"""Brace — +2 OCV that only offsets the Range Modifier; ½ DCV (6E2 p62)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import ActionDeclared, ActionResolved, make_author_combatant

# Per 6E2 p62 §BRACE — Brace grants +2 OCV that only offsets the Range
# Modifier. The bonus cannot produce a positive net OCV contribution from
# the range axis (it caps the effective range modifier at 0).
_RANGE_OFFSET_BONUS = 2
_DCV_FACTOR = 0.5


def apply_brace_to_range_modifier(range_modifier: int) -> int:
    """Apply the Brace +2 range-offset to a raw range modifier.

    Per 6E2 p62 §BRACE, Brace grants +2 OCV "that only offsets the Range
    Modifier" — the bonus only applies against negative range penalties and
    cannot push the effective range contribution above 0.

    Examples:
        range_modifier = -3  → effective = -1 (offset by +2)
        range_modifier = -1  → effective =  0 (offset by +2, capped)
        range_modifier =  0  → effective =  0 (no positive bonus added)
    """
    return min(0, range_modifier + _RANGE_OFFSET_BONUS)


class Brace:
    """Brace tactical modifier.

    Per 6E2 p62 §BRACE:
    - Grants +2 OCV that *only* offsets the Range Modifier (capped at 0).
    - Imposes ½ DCV on the bracer.
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

        Per 6E2 p62 §BRACE, the returned dict carries:
          - "range_offset_bonus": +2 OCV that only offsets the Range Modifier
            (consumers should call ``apply_brace_to_range_modifier``).
          - "dcv_factor": 0.5 (½ DCV while bracing).
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
            "range_offset_bonus": _RANGE_OFFSET_BONUS,
            "dcv_factor": _DCV_FACTOR,
        }
