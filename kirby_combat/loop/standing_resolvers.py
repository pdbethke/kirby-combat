"""Resolvers for the standing powers (`kirby_combat/standing_areas.py`).

In their own module, beside `loop/resolvers.py` rather than inside it, so
the batch that added them touches the shared registry file not at all.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import ResolvedAction, resolves
from kirby_combat.standing_areas import RAISE_DAMAGE_SHIELD, raise_damage_shield

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate


@resolves(RAISE_DAMAGE_SHIELD)
def _resolve_raise_damage_shield(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Switch a Damage Shield on (6E1 p.323): a Zero Phase Action."""
    power = action._attack_view
    if power is None:
        raise ValueError(f"{action.action_id!r} carries no power to raise")
    before = len(session.event_log)
    new_session = raise_damage_shield(session, actor, power,
                                      template=template, roller=roller)
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=None, events=list(new_session.event_log[before:]),
    )
