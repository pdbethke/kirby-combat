"""Resolvers for the offers `half_phase_offers` and `entangle_offers` add.

In their own module, beside `loop/resolvers.py` rather than inside it, the way
`standing_resolvers.py` and `autofire_resolvers.py` are, so this batch touches
the shared registry file as little as it can.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kirby_combat.entangle_offers import (
    ATTACK_ENTANGLE, TARGETED_ENTANGLE_OCV, TARGETED_PARALYSIS_DMCV,
)
from kirby_combat.enumeration import LegalAction
from kirby_combat.half_phase_offers import HALF_MOVE, SNAP_OUT_OF_RAGE
from kirby_combat.loop.registry import ResolvedAction, UnresolvableAction, resolves

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate


@resolves(HALF_MOVE)
def _resolve_half_move(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Close on the named man with up to half his movement (6E2 p.26).

    Where he ends up is `movement_reach`'s answer, as for the Full Move; the
    difference is the allowance, and that the Phase is still his after it.
    """
    from kirby_combat.loop.resolvers import (
        _events_since, _half_move, _reach_of, _recorded, _stop_at_reach,
    )
    from kirby_combat.placement import move_toward
    from kirby_world.occupancy import position_of

    mode = action.mode
    if mode is None:
        raise UnresolvableAction(action.kind, action.action_id)
    destination = position_of(session.scene, action.target_id)
    if destination is None:
        raise UnresolvableAction(action.kind, action.action_id)
    # To within Reach of him, not onto him (6E2 p.56).
    destination = _stop_at_reach(position_of(session.scene, actor.id),
                                 destination, _reach_of(actor, action))
    moved, outcome = move_toward(
        session, actor.id, destination, mode=mode,
        distance_m=_half_move(actor, mode), template=template,
    )
    if outcome is None:
        raise UnresolvableAction(action.kind, action.action_id)
    out = _recorded(moved, actor, action, outcome, {
        "kind": action.kind, "target_id": action.target_id, "mode": mode,
        "reached": outcome.reachable, "phase": "half",
        "landing": [outcome.landing.x, outcome.landing.y, outcome.landing.z],
    })
    from dataclasses import replace

    # The `MovementResolved` the move wrote is part of this step.
    return replace(out, events=_events_since(session, out.session))


@resolves(SNAP_OUT_OF_RAGE)
def _resolve_snap_out_of_rage(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Somebody tries to snap him out of it: he rolls to recover (6E1 p.424).

    The attempt is the caller's Action; the roll is the raging man's own
    recovery roll, `RageRolled(reason="snapped_out")`, and it counts as his
    attempt this Turn for the free Post-Segment 12 one ("if he hasn't
    attempted to recover in that Turn").
    """
    from kirby_combat.loop.resolvers import _events_since, _record_outcome
    from kirby_combat.rage import RecoveryOccasion, rage_state, try_to_recover

    raging = session.combatants.get(action.target_id or "")
    if raging is None or not rage_state(session, raging.id).raging:
        raise UnresolvableAction(action.kind, action.action_id)
    s = _record_outcome(session, actor, action, {
        "kind": action.kind, "target_id": raging.id,
    })
    s = try_to_recover(s, raging.id, RecoveryOccasion.SNAPPED_OUT, roller)
    calmed = not rage_state(s, raging.id).raging
    return ResolvedAction(
        session=s, kind=action.kind, action_id=action.action_id,
        result=calmed, events=_events_since(session, s),
    )


@resolves(ATTACK_ENTANGLE)
def _resolve_attack_entangle(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Attack the Entangle holding an ally, not the ally (6E1 p.218-219).

    Physical: an Attack Roll at -3 OCV against the Entangle's DCV 0, the
    power's BODY against the Entangle's PD or ED as the power targets.
    Mental Paralysis: a Mental Blast's MCV Attack Roll against DMCV 3, its
    dice counted as Normal Damage BODY against the paralysis's Mental Defense
    ("if it's a STUN-only attack, count the 'BODY' as if it were a Normal
    Damage attack"). The attacker pays the power's END either way.
    """
    from kirby_combat.actions.entangle import Entangle, counted_body, escape_body
    from kirby_combat.actions.recording import _fold_session_cvs, _spend_attack_end
    from kirby_combat.endurance import end_cost
    from kirby_combat.loop.resolvers import (
        _events_since, _record_outcome, _with_half_die,
    )
    from kirby_combat.models import AttackInput, DiceValues
    from kirby_combat.resolution.damage import compute_damage

    power = action._attack_view
    victim = session.combatants.get(action.target_id or "")
    if power is None or victim is None:
        raise UnresolvableAction(action.kind, action.action_id)
    paralysis = action.action_id.startswith(f"{ATTACK_ENTANGLE}:paralysis:")
    hold = Entangle.held(session, victim.id, mental_paralysis=paralysis)
    if hold is None:
        raise UnresolvableAction(action.kind, action.action_id)

    if paralysis:
        from kirby_combat.cv_modifiers import effective_omcv_for
        from kirby_combat.mental.mental_combat import resolve_mental_to_hit

        omcv_delta = effective_omcv_for(session, actor.id) - int(actor.omcv)
        to_hit = resolve_mental_to_hit(
            actor, victim, roller.roll_dice(3), ocv_modifier=omcv_delta,
            # The paralysis's DMCV 3, not the man's.
            dcv_modifier=TARGETED_PARALYSIS_DMCV - int(victim.dmcv),
        )
        record = {"hit": bool(to_hit.hit), "roll": int(to_hit.roll),
                  "target_number": int(to_hit.target_number),
                  "dmcv": TARGETED_PARALYSIS_DMCV}
    else:
        from kirby_combat.resolution.to_hit import resolve_to_hit
        from kirby_combat.loop.run import distances_from

        distance = (distances_from(session.scene, actor, [victim]) or {}).get(victim.id)
        # The Entangle's DCV 0 is the man's own while he is in it (6E1
        # p.217: Entangled, "a DCV of 0"), and the fold puts him there; the
        # -3 OCV is targeting the thing rather than the man (p.218).
        attack = _fold_session_cvs(session, AttackInput(
            attacker=actor, target=victim, power=power, distance_m=distance,
            aim=None, dice=DiceValues(to_hit=roller.roll_dice(3)),
            ocv_modifier=TARGETED_ENTANGLE_OCV,
        ))
        to_hit = resolve_to_hit(attack, template)
        record = {"hit": bool(to_hit.hit), "roll": int(to_hit.roll),
                  "target_number": int(to_hit.target_number),
                  "effective_ocv": int(to_hit.effective_ocv),
                  "target_dcv": int(to_hit.effective_dcv)}

    s = _spend_attack_end(session, actor, end_cost(power), template, power=power)
    if not to_hit.hit:
        s = _record_outcome(s, actor, action, {
            "kind": action.kind, "target_id": victim.id, "paralysis": paralysis,
            **record,
        })
        return ResolvedAction(session=s, kind=action.kind, action_id=action.action_id,
                              result=to_hit, events=_events_since(session, s))

    whole = max(1, int(getattr(power, "damage_dice", 0) or 0))
    if paralysis:
        body = counted_body(roller.roll_dice(whole))
        defense = hold.md
    else:
        body = compute_damage(
            power, DiceValues(damage=roller.roll_dice(_with_half_die(power, whole))),
            template).body
        defense = hold.ed if power.defense_type == "ed" else hold.pd
    through = escape_body(body, defense)
    s = _record_outcome(s, actor, action, {
        "kind": action.kind, "target_id": victim.id, "paralysis": paralysis,
        **record, "body": body, "defense": defense, "body_through": through,
    })
    s, result = Entangle.attacked_from_outside(
        s, attacker_id=actor.id, target_id=victim.id, damage_body=through,
        mental_paralysis=paralysis,
    )
    return ResolvedAction(session=s, kind=action.kind, action_id=action.action_id,
                          result=result, events=_events_since(session, s))
