"""Set — +1 OCV on next ranged attack (6E2 pg 75).

Named set_action.py to avoid shadowing Python's built-in `set`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import ActionDeclared, ActionResolved, make_author_combatant

_OCV_BONUS = 1


class Set:
    """Set action tactical modifier.

    Declares intent to aim carefully at a target. Grants +1 OCV on the next
    ranged attack only (the bonus is consumed when the attack resolves).
    """

    name: str = "set"

    @staticmethod
    def declare(
        session: CombatSession,
        combatant_id: str,
        *,
        target_id: str | None = None,
    ) -> tuple[CombatSession, ActionDeclared]:
        """Record a Set declaration.

        Emits ActionDeclared(action_type="set").
        """
        from kirby_combat.session.apply import apply_event

        params: dict[str, Any] = {}
        if target_id is not None:
            params["target_id"] = target_id

        evt = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(combatant_id),
            combatant_id=combatant_id,
            action_type="set",
            targets=[target_id] if target_id else [],
            parameters=params,
        )
        return apply_event(session, evt), evt

    @staticmethod
    def ocv_bonus(session: CombatSession, combatant_id: str,
                  target_id: str | None = None) -> int:
        """Return +1 if a Set against `target_id` is pending, else 0.

        "Pending" means the most recent Set declaration has no
        corresponding ActionResolved.

        THE TARGET IS PART OF THE RULE. 6E2 p.81 grants the bonus "to all
        attacks against that target until he loses his Set" --- not to
        whatever the attacker swings at next. This ignored the target
        entirely, so a man who drew a bead on Wyatt Earp shot Ike Clanton
        more accurately for it.

        `target_id=None` asks the old question -- "is a Set pending at
        all" -- and is kept for callers that only want to know whether
        the Set is still standing.
        """
        declaration_id: str | None = None
        for evt in reversed(session.event_log):
            if (
                isinstance(evt, ActionDeclared)
                and evt.combatant_id == combatant_id
                and evt.action_type == "set"
            ):
                # The event keeps its victim in `targets` (and in
                # `parameters`), NOT as a `target_id` attribute --- a first
                # draft read `getattr(evt, "target_id", None)`, got None
                # for every Set ever declared, and so reported no bonus
                # at all while the tests for the offer stayed green.
                declared_on = list(evt.targets or [])
                if target_id is not None and target_id not in declared_on:
                    # The most recent Set names somebody else. A Set is
                    # lost when a new one is declared, so an older Set on
                    # this target is no longer standing either.
                    return 0
                declaration_id = evt.id
                break

        if declaration_id is None:
            return 0

        # Check if already resolved.
        for evt in session.event_log:
            if (
                isinstance(evt, ActionResolved)
                and evt.declaration_event_id == declaration_id
            ):
                return 0

        return _OCV_BONUS
