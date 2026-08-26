"""GM-authored attacks — NPC actions or PC actions on behalf of an absent player.

A GMAttackDeclaration is the same shape as a normal ActionDeclared event but
carries an `author` of type "gm" and an optional `on_behalf_of` field for
absent-PC scenarios.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from kirby_combat.models import StatBlockCombatant
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, EventAuthor, make_author_gm,
)


@dataclass
class GMAttackDeclaration:
    """Wrapper around an ActionDeclared event for GM-authored attacks."""
    declaration: ActionDeclared
    on_behalf_of: str | None = None     # combatant_id of absent PC, if any


def make_gm_attack(
    session: CombatSession,
    user_id: str,
    actor_id: str,
    target_ids: list[str],
    action_type: str = "attack",
    parameters: dict[str, Any] | None = None,
    on_behalf_of: str | None = None,
) -> GMAttackDeclaration:
    """Build a GM-authored ActionDeclared.

    `actor_id` is the combatant whose stats will be used (the NPC, or the
    absent PC). `on_behalf_of` is set when GMing for an absent PC.
    """
    actor = session.combatants.get(actor_id)
    if actor is None:
        raise KeyError(f"GM attack: unknown actor {actor_id}")
    seq = len(session.event_log) + 1
    params = dict(parameters or {})
    if on_behalf_of:
        params["on_behalf_of"] = on_behalf_of
    decl = ActionDeclared(
        id=f"{session.id}-evt-{seq}",
        session_id=session.id,
        sequence=seq,
        timestamp=datetime.now(timezone.utc),
        author=make_author_gm(user_id),
        combatant_id=actor_id,
        action_type=action_type,
        targets=list(target_ids),
        parameters=params,
    )
    return GMAttackDeclaration(declaration=decl, on_behalf_of=on_behalf_of)


def can_actor_pay_end(actor: StatBlockCombatant, end_cost: int) -> bool:
    """A GM-attack still respects the actor's current END."""
    return actor.current_end >= end_cost
