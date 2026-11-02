"""Setting off a Self Only damaging power (squad tactics spec, 7).

The power's damage is rolled, defended and applied to the man who set it off
and to nobody else: "Self Only" (`power_modifiers.CustomLimitation`) means it
affects only its user, so an enemy next to him loses nothing. The damage goes
through the engine's one damage path (`recording._apply_damage`) with
``caused_by`` his own id, so the record shows he did it.

The use is a Charge spent like any other: the row carries ``power_source_id``
and `charges.spent_charges` counts it. No END is paid: the Charge is the cost
(RULING: the power exists to be used once, at the end).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import ResolvedAction, UnresolvableAction, resolves
from kirby_combat.self_destruct import SELF_DESTRUCT

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate


@resolves(SELF_DESTRUCT)
def _resolve_self_destruct(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Roll the power's damage, take it through his own defences, spend the
    Charge. Nobody else is touched."""
    from kirby_combat.actions.recording import _apply_damage
    from kirby_combat.loop.resolvers import (
        _attack_dice, _events_since, _recorded, _with_half_die,
    )
    from kirby_combat.resolution.damage import compute_damage
    from kirby_combat.resolution.defense import compute_defense

    power = action._attack_view
    if power is None:
        raise UnresolvableAction(action.kind, action.action_id)
    me = session.combatants[actor.id]
    dice = _attack_dice(roller, _with_half_die(power, max(1, int(power.damage_dice))))
    damage = compute_damage(power, dice, template)
    defense = compute_defense(me, power)
    stun = max(0, damage.stun - defense.total_defense)
    body = max(0, damage.body - defense.total_defense)
    if defense.damage_reduction_pct > 0:
        kept = (100 - defense.damage_reduction_pct) / 100.0
        stun, body = int(stun * kept), int(body * kept)
    after = _apply_damage(session, actor.id, stun=stun, body=body, caused_by=actor.id)
    out = _recorded(after, actor, action, None, {
        "kind": SELF_DESTRUCT, "target_id": actor.id,
        "stun_dealt": stun, "body_dealt": body,
        "power_xmlid": power.xmlid, "power_name": power.name,
        "power_source_id": getattr(power, "source_id", None),
        "damage_type": power.damage_type,
    })
    from dataclasses import replace

    return replace(out, events=_events_since(session, out.session))
