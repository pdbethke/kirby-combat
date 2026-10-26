"""Session-recording wrappers for the mental powers.

WHY THESE DID NOT EXIST. ``mental/mind_control.py``, ``mental_illusion.py``
and ``telepathy.py`` have held correct, tested resolvers for a long time ---
and nothing in production ever called them. The parked kirby-api driver
wrote its own version of each inside its 1,070-line dispatcher, so the
engine's copies were reachable only from their own unit tests.

The measurement that makes the point (2026-09-06): the engine states the
mental Attack Roll once, in ``mental_combat.py`` --- "Target number = 11 +
attacker.omcv - target.dmcv + modifiers". The parked driver writes that
same expression out at four separate lines: 8619, 9592, 9706 and 11172.

**Nothing caught it because every one of those suites is green.** The
engine's rules are correct and tested; what was missing is a caller. No
test asserts "something reaches this", which is exactly the shape of defect
the resolver registry now makes countable --- ``registered_kinds()`` moving
is the assertion that was never there.

WHAT THESE ADD, AND WHAT THEY DELIBERATELY DO NOT. Each wrapper runs the
pure resolver UNCHANGED and records an ``ActionResolved`` carrying its
outcome --- and the MCV Attack Roll that let it through (`attack_roll.py`;
a miss never reaches these, see `record_mental_miss`). None of them applies
an effect to combatant state. Mind Control and Mind Scan record
``established`` and the facts their lasting effect needs (who, the order,
the lock's level, the Breakout modifier); `mental/continuing.py` folds those
payloads forward, so the payload IS the effect rather than a second record
of it. Mental Illusions do the same with the illusion they cast. Telepathy
still changes nothing after the roll.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from kirby_combat.mental.mental_combat import MentalToHitResult
from kirby_combat.mental.mental_illusion import resolve_mental_illusion
from kirby_combat.mental.mind_control import resolve_mind_control
from kirby_combat.mental.mind_scan import resolve_mind_scan
from kirby_combat.mental.telepathy import resolve_telepathy
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_combatant,
)

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


def _declare(
    session: "CombatSession", attacker_id: str, target_id: str,
    action_type: str, declaration_event_id: str | None, now: datetime,
) -> tuple["CombatSession", str]:
    """Emit an ``ActionDeclared`` unless the caller already declared one."""
    if declaration_event_id is not None:
        return session, declaration_event_id
    declared = ActionDeclared(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=now,
        author=make_author_combatant(attacker_id),
        combatant_id=attacker_id,
        action_type=action_type,
        targets=[target_id],
        parameters={},
    )
    return apply_event(session, declared), declared.id


def _record(
    session: "CombatSession", attacker_id: str, decl_id: str,
    payload: dict[str, Any], now: datetime,
) -> "CombatSession":
    resolved = ActionResolved(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=now,
        author=make_author_combatant(attacker_id),
        declaration_event_id=decl_id,
        result_payload=payload,
    )
    return apply_event(session, resolved)


def to_hit_payload(to_hit: MentalToHitResult) -> dict[str, Any]:
    """The MCV Attack Roll as it reaches a payload --- one shape for all."""
    return {
        "hit": to_hit.hit,
        "roll": to_hit.roll,
        "target_number": to_hit.target_number,
        "omcv": to_hit.effective_ocv,
        "dmcv": to_hit.effective_dcv,
    }


def record_mental_miss(
    session: "CombatSession", attacker, target, to_hit: MentalToHitResult, *,
    action_type: str,
) -> "CombatSession":
    """A Mental Power whose MCV Attack Roll missed: declared, rolled, nothing.

    No Effect Roll is made (6E1 p.151: the Effect Roll follows "a successful
    MCV Attack Roll"), so no effect dice are drawn either.
    """
    now = datetime.now(timezone.utc)
    s, decl_id = _declare(session, attacker.id, target.id, action_type, None, now)
    return _record(s, attacker.id, decl_id, {
        "kind": action_type,
        "target_id": target.id,
        **to_hit_payload(to_hit),
    }, now)


def resolve_mind_control_in_session(
    session: "CombatSession", attacker, target, effect_dice_values: list[int],
    *, order: str, source_id: str, to_hit: MentalToHitResult,
    declaration_event_id: str | None = None, action_type: str = "mind_control",
):
    """Resolve Mind Control for ``order`` and record whether it took hold.

    An established payload is the effect itself: `continuing.py` reads its
    ``attacker_id``, ``order`` and ``breakout_modifier`` forward until the
    target breaks out.
    """
    now = datetime.now(timezone.utc)
    result = resolve_mind_control(attacker, target, effect_dice_values, order=order)
    s, decl_id = _declare(
        session, attacker.id, target.id, action_type, declaration_event_id, now,
    )
    s = _record(s, attacker.id, decl_id, {
        "kind": action_type,
        "target_id": target.id,
        "attacker_id": attacker.id,
        **to_hit_payload(to_hit),
        "order": result.order,
        "required_total": result.required_total,
        "effect_rolled": result.effect_rolled,
        "effect_total": result.effect_total,
        "degree": result.degree,
        "target_ego": result.target_ego,
        "established": result.established,
        "breakout_modifier": result.breakout_modifier,
        "source_id": source_id,
    }, now)
    return s, result


def resolve_mind_scan_in_session(
    session: "CombatSession", attacker, target, effect_dice_values: list[int],
    *, desired: str, source_id: str, to_hit: MentalToHitResult,
    action_type: str = "mind_scan",
):
    """Resolve a Mind Scan's Effect Roll and record the lock, if one formed.

    ``source_id`` is the Mind Scan power's own id, which is how
    `continuing.py` tells that the scanner later switched it off.
    """
    now = datetime.now(timezone.utc)
    result = resolve_mind_scan(attacker, target, effect_dice_values, desired=desired)
    s, decl_id = _declare(session, attacker.id, target.id, action_type, None, now)
    s = _record(s, attacker.id, decl_id, {
        "kind": action_type,
        "target_id": target.id,
        "attacker_id": attacker.id,
        **to_hit_payload(to_hit),
        "desired": result.desired,
        "required_total": result.required_total,
        "effect_rolled": result.effect_rolled,
        "effect_total": result.effect_total,
        "reached": result.reached,
        "target_ego": result.target_ego,
        "established": result.established,
        "breakout_modifier": result.breakout_modifier,
        "source_id": source_id,
    }, now)
    return s, result


def resolve_mental_illusion_in_session(
    session: "CombatSession", attacker, target, effect_dice_values: list[int],
    *, illusion, power_active_points: int, source_id: str,
    to_hit: MentalToHitResult,
    declaration_event_id: str | None = None, action_type: str = "mental_illusion",
):
    """Resolve a Mental Illusion for ``illusion`` and record whether it took hold.

    Like Mind Control, an established payload is the effect itself:
    `continuing.py` folds its ``illusion`` and ``breakout_modifier`` forward
    until the target sees through it, and a harmful one's ``illusion_dice``
    are rolled when he first fails to (6E1 p.253).
    """
    now = datetime.now(timezone.utc)
    result = resolve_mental_illusion(
        attacker, target, effect_dice_values,
        illusion=illusion, power_active_points=power_active_points,
    )
    s, decl_id = _declare(
        session, attacker.id, target.id, action_type, declaration_event_id, now,
    )
    s = _record(s, attacker.id, decl_id, {
        "kind": action_type,
        "target_id": target.id,
        "attacker_id": attacker.id,
        **to_hit_payload(to_hit),
        "illusion": result.illusion,
        "required_total": result.required_total,
        "effect_rolled": result.effect_rolled,
        "effect_total": result.effect_total,
        "degree": result.degree,
        "target_ego": result.target_ego,
        "established": result.established,
        "breakout_modifier": result.breakout_modifier,
        "illusion_dice": result.illusion_dice,
        "source_id": source_id,
    }, now)
    return s, result


def resolve_telepathy_in_session(
    session: "CombatSession", attacker, target, effect_dice_values: list[int],
    *, to_hit: MentalToHitResult, target_has_mental_awareness: bool = False,
    declaration_event_id: str | None = None, action_type: str = "telepathy",
):
    """Resolve Telepathy and record what was read.

    ``target_has_mental_awareness`` is passed through unchanged --- whether
    the target notices is the pure resolver's call, not this wrapper's.
    """
    now = datetime.now(timezone.utc)
    result = resolve_telepathy(
        attacker, target, effect_dice_values,
        target_has_mental_awareness=target_has_mental_awareness,
    )
    s, decl_id = _declare(
        session, attacker.id, target.id, action_type, declaration_event_id, now,
    )
    s = _record(s, attacker.id, decl_id, {
        "kind": action_type,
        "target_id": target.id,
        **to_hit_payload(to_hit),
        "effect_total": result.effect_total,
        "degree": result.degree,
        "target_ego": result.target_ego,
        "target_is_aware": result.target_is_aware,
    }, now)
    return s, result


def illusion_strikes(session: "CombatSession", effect, roller) -> "CombatSession":
    """A harmful Mental Illusion's one attack, as the victim first believes it.

    6E1 p.253: Normal Damage of ``illusion_dice`` (sized when it was cast, the
    lesser of the Effect Roll and the power's Active Points, /5), against
    the defense the illusory attack calls for (`ILLUSORY_ATTACK_DEFENSE`).
    STUN only unless it was cast at the BODY-and-STUN level. "Illusory
    attacks never do Knockback" --- none is rolled.

    Recorded the way a Mental Blast's damage is: a `VitalsChanged` through
    `_apply_damage`, then an ``ActionResolved`` (kind
    ``mental_illusion_damage``) whose ``status_changes`` let a Stun or a
    knockout fold exactly as any other attack's do. It points at the
    illusion's own declaration, since this is that action landing.
    """
    from kirby_combat.actions.recording import _apply_damage
    from kirby_combat.adjustments import adjusted_con
    from kirby_combat.mental.mental_illusion import (
        ILLUSORY_ATTACK_DEFENSE, IllusoryHarm, illusion_named,
    )
    from kirby_combat.models import AttackPower, DiceValues
    from kirby_combat.resolution.damage import compute_damage
    from kirby_combat.resolution.defense import compute_defense
    from kirby_combat.resolution.status import determine_status_changes

    illusion = illusion_named(effect.illusion)
    if illusion.harm is None:
        return session
    cast = next(e for e in session.event_log if e.id == effect.effect_id)
    dice = int(cast.result_payload["illusion_dice"])
    target = session.combatants[effect.target_id]
    phantom = AttackPower(
        xmlid="MENTALILLUSION", name="illusory attack", damage_dice=dice,
        half_die=False, plus_one=False, damage_type="normal",
        defense_type=ILLUSORY_ATTACK_DEFENSE, range_m=None, uses_str=False,
        str_min=0, armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id=None,
    )
    stun = body = 0
    if dice > 0:                # under 5 points of effect buys no die at all
        rolled = compute_damage(phantom, DiceValues(damage=roller.roll_dice(dice)),
                                session.template)
        defense = compute_defense(target, phantom).total_defense
        stun = max(0, rolled.stun - defense)
        if illusion.harm is IllusoryHarm.STUN_AND_BODY:
            body = max(0, rolled.body - defense)
    s = _apply_damage(session, target.id, stun=stun, body=body)
    status_changes = determine_status_changes(
        stun_before=target.current_stun, stun_after=target.current_stun - stun,
        body_before=target.current_body, body_after=target.current_body - body,
        con=adjusted_con(s, target), max_body=target.max_body,
    )
    return _record(s, effect.attacker_id, cast.declaration_event_id, {
        "kind": "mental_illusion_damage",
        "target_id": target.id,
        "attacker_id": effect.attacker_id,
        "effect_id": effect.effect_id,
        "illusion": illusion.name,
        "stun_dealt": stun,
        "body_dealt": body,
        "status_changes": status_changes,
    }, datetime.now(timezone.utc))
