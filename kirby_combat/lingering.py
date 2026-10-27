"""Attacks that go on hurting: Constant and Damage Over Time.

WHAT THE DELETED DRIVER DID. kirby-api's `_add_continuous_effect` /
`_fire_continuous_effects` kept a list of effects in a JSON column on the
combatant row and fired them at the start of the VICTIM's Phase: roll the
dice, subtract PD (or ED, or MD), take that much STUN --- no BODY, no
Killing damage, no Stun. Before each it gave the victim a CON Roll to
"shake off" the effect, citing "6E1 p102". A plain Constant power lasted a
flat 4 Phases.

Almost none of that is in the book, and this module does not port it:

  * THERE IS NO CON SHAKE-OFF. 6E1 p.102 is not about Constant powers and
    no page gives a victim a CON Roll against one. 6E1 p.129 ends a Constant
    attack when "the attacker turns off the Power, stops maintaining it
    (i.e., stops paying END for it), or loses LOS to the target"; 6E1 p.333
    ends a Damage Over Time when it runs its course, is negated by its
    stated counter, or is Adjusted to 0 Active Points. Nothing the victim
    rolls.
  * A CONSTANT ATTACK FIRES ON THE ATTACKER'S PHASES (6E1 p.129: "in every
    Segment in which the attacker has a Phase (on the attacker's DEX)"),
    and lasts as long as he maintains it --- not four Phases.
  * A DAMAGE OVER TIME FIRES ON ITS OWN CLOCK (6E1 p.331: "the first
    increment of damage affects the target one time period after the
    character uses the attack"), in whatever Segment that falls, and the
    attack itself does no damage: "if a character wanted the power to
    affect the target once when it was used, he could buy a Linked attack".
  * EACH DOSE IS THE WHOLE ATTACK: its dice, the victim's defenses "to each
    damage increment" (6E1 p.332), Killing or Normal, BODY and STUN, and it
    can Stun him. So each one goes through the attack door
    (`recording.resolve_attack_in_session`) with no Attack Roll ("The
    attacker doesn't have to make further Attack Rolls", 6E1 p.129) and the
    use already paid for.
  * AVAD/NND (the driver's cobra venom) needs nothing here: the door's
    damage pipeline already applies the alternate defense and STUN-only.

The record is the house pattern (`session/effects.py`): a
`LingeringAttackApplied`, each dose an `ActionResolved` declared by it and
carrying the absolute ``increments_remaining``, and a
`LingeringAttackEnded`. `lingering_effects` folds them forward.

RULINGS, where the book leaves the call to the table (each labelled where
it is made): the attacker keeps maintaining a Constant attack while he can
(nothing in the engine chooses to switch one off), stops when its target is
out of the fight, and a fresh use of the same power ends the old one; a
Damage Over Time's "can be negated by" condition is free text the engine
cannot act on, so nothing negates it in a fight.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from kirby_combat.encounter import SEGMENTS_PER_TURN

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


class LingeringMode(str, Enum):
    CONSTANT = "constant"
    DAMAGE_OVER_TIME = "damage_over_time"


class LingeringEnd(str, Enum):
    """Why a lingering attack stopped (`LingeringAttackEnded.reason`)."""

    RAN_ITS_COURSE = "ran_its_course"          # 6E1 p.331
    NO_END = "could_not_pay_end"               # 6E1 p.129
    LOST_LINE_OF_SIGHT = "lost_line_of_sight"  # 6E1 p.129
    ATTACKER_STUNNED = "attacker_stunned_or_out"   # 6E1 p.347
    SLOT_SWITCHED = "slot_switched_off"        # 6E1 p.400
    TARGET_DOWN = "target_out_of_the_fight"    # RULING
    POWER_REUSED = "power_used_again"          # RULING
    POWER_NOT_ON_BUILD = "power_not_on_build"


@dataclass(frozen=True)
class Lingering:
    """One lingering attack, as the log has it now."""

    id: str
    attacker_id: str
    target_id: str
    power_source_id: str
    mode: LingeringMode
    increments: int | None
    interval_segments: int | None
    applied_at: int              # absolute Segment, see `absolute_segment`
    applied_seq: int
    doses: int
    increments_remaining: int | None
    ended: bool


def absolute_segment(turn: int, segment: int) -> int:
    """Segments since the start of Turn 1 (6E2 p.18: twelve to a Turn)."""
    return (int(turn) - 1) * SEGMENTS_PER_TURN + int(segment)


def lingering_effects(session: "CombatSession") -> list[Lingering]:
    """Every lingering attack in this fight, folded forward from the log."""
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for event in session.event_log:
        kind = getattr(event, "kind", "")
        if kind == "LingeringAttackApplied":
            by_id[event.id] = {
                "id": event.id, "attacker_id": event.attacker_id,
                "target_id": event.target_id,
                "power_source_id": event.power_source_id,
                "mode": LingeringMode(event.mode),
                "increments": event.increments,
                "interval_segments": event.interval_segments,
                "applied_at": absolute_segment(event.applied_turn,
                                               event.applied_segment),
                "applied_seq": event.sequence,
                "doses": 0, "increments_remaining": event.increments,
                "ended": False,
            }
            order.append(event.id)
        elif kind == "ActionResolved":
            payload = getattr(event, "result_payload", None) or {}
            lid = payload.get("lingering_id")
            if lid in by_id:
                by_id[lid]["doses"] += 1
                if payload.get("increments_remaining") is not None:
                    by_id[lid]["increments_remaining"] = int(
                        payload["increments_remaining"])
        elif kind == "LingeringAttackEnded":
            if event.lingering_id in by_id:
                by_id[event.lingering_id]["ended"] = True
    return [Lingering(**by_id[i]) for i in order]


def active_lingering(session, *, attacker_id: str | None = None,
                     target_id: str | None = None,
                     mode: LingeringMode | None = None) -> list[Lingering]:
    return [
        e for e in lingering_effects(session)
        if not e.ended
        and (attacker_id is None or e.attacker_id == attacker_id)
        and (target_id is None or e.target_id == target_id)
        and (mode is None or e.mode is mode)
    ]


def locked_out(session, attacker_id: str, power, target_id: str) -> bool:
    """6E1 p.332's Lock Out: "one use of the Damage Over Time attack 'locks
    out' the attack for further use on that target until the first use
    stops affecting him"."""
    dot = getattr(power, "damage_over_time", None)
    if dot is None or not dot.lockout:
        return False
    source = str(getattr(power, "source_id", "") or "")
    return any(e.power_source_id == source for e in active_lingering(
        session, attacker_id=attacker_id, target_id=target_id,
        mode=LingeringMode.DAMAGE_OVER_TIME))


def mode_of(power) -> LingeringMode | None:
    if getattr(power, "damage_over_time", None) is not None:
        return LingeringMode.DAMAGE_OVER_TIME
    if getattr(power, "constant", False):
        return LingeringMode.CONSTANT
    return None


# ---------------------------------------------------------------------------
# Writing it down
# ---------------------------------------------------------------------------

def _apply(session, event):
    from kirby_combat.session.apply import apply_event

    return apply_event(session, event)


def _end(session, lingering_id: str, reason: LingeringEnd):
    from kirby_combat.session.events import LingeringAttackEnded, make_author_engine

    return _apply(session, LingeringAttackEnded(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        lingering_id=lingering_id, reason=reason.value,
    ))


def begin_lingering(session, *, attacker_id: str, target_id: str, power):
    """Record that a Constant or Damage Over Time attack has hit.

    A Constant power used again ends the attacker's earlier maintenance of
    it (RULING: one power, one maintained effect --- 6E1 p.129 keeps "the
    Power" on a target, and a second activation is a new use of it).
    """
    from kirby_combat.session.events import LingeringAttackApplied, make_author_combatant

    mode = mode_of(power)
    if mode is None:
        raise ValueError(f"power {getattr(power, 'name', '?')!r} neither "
                         "Constant nor Damage Over Time")
    source = str(getattr(power, "source_id", "") or "")
    if not source:
        raise ValueError(
            f"lingering power {getattr(power, 'name', '?')!r} has no "
            "source_id; a later dose has to find the power again by its id")
    if mode is LingeringMode.CONSTANT:
        for old in active_lingering(session, attacker_id=attacker_id,
                                    mode=LingeringMode.CONSTANT):
            if old.power_source_id == source:
                session = _end(session, old.id, LingeringEnd.POWER_REUSED)
    dot = getattr(power, "damage_over_time", None)
    return _apply(session, LingeringAttackApplied(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(attacker_id),
        attacker_id=attacker_id, target_id=target_id,
        power_source_id=source, power_name=str(getattr(power, "name", "")),
        mode=mode.value,
        increments=dot.increments if dot is not None else None,
        interval_segments=dot.interval_segments if dot is not None else None,
        applied_turn=session.timeline.turn,
        applied_segment=session.timeline.segment,
    ))


def _power_of(session, effect: Lingering):
    attacker = session.combatants.get(effect.attacker_id)
    if attacker is None:
        return None
    attacks = attacker.attacks
    attacks = attacks() if callable(attacks) else attacks
    for ap in attacks or []:
        if str(getattr(ap, "source_id", "") or "") == effect.power_source_id:
            return ap
    return None


def _dose(session, effect: Lingering, power, *, template, roller,
          increments_remaining: int | None):
    """One dose: the attack's damage, no Attack Roll, already paid for."""
    dot = getattr(power, "damage_over_time", None)
    if (effect.mode is LingeringMode.DAMAGE_OVER_TIME and dot is not None
            and dot.one_defense):
        return _dose_against_one_defense(
            session, effect, power, template=template, roller=roller,
            increments_remaining=increments_remaining)
    from kirby_combat.actions.recording import resolve_attack_in_session
    from kirby_combat.models import AttackInput, DiceValues, ToHitResult

    attacker = session.combatants[effect.attacker_id]
    target = session.combatants[effect.target_id]
    page = "6E1 p.129" if effect.mode is LingeringMode.CONSTANT else "6E1 p.331"
    fixed = ToHitResult(
        hit=True, roll=0, target_number=0, margin=0,
        effective_ocv=0, effective_dcv=0, range_penalty=0,
        hit_location_penalty=0, csl_bonus=0,
        audit=[f"{effect.mode.value}: no further Attack Roll ({page})"],
    )
    bare = replace(power, constant=False, damage_over_time=None, area=None,
                   side_effects=None)
    count = max(1, int(bare.damage_dice or 0)) + (1 if bare.half_die else 0)
    attack = AttackInput(
        attacker=attacker, target=target, power=bare, distance_m=None,
        aim=None,
        dice=DiceValues(
            to_hit=[], damage=roller.roll_dice(count),
            hit_location=roller.roll_dice(3), stun_multiplier=roller.roll_dice(1),
        ),
        fixed_to_hit=fixed,
    )
    session, _ = resolve_attack_in_session(
        session, attack, template, declaration_event_id=effect.id,
        action_type="attack", roller=roller, paid_use_event_id=effect.id,
        payload_extras=lambda _r: {
            "lingering_id": effect.id,
            "lingering_mode": effect.mode.value,
            "increments_remaining": increments_remaining,
        },
    )
    return session


def _absorbed_so_far(session, effect: Lingering) -> tuple[int, int]:
    """STUN and BODY the victim's defense has already soaked from this one
    Damage Over Time (6E1 p.332's "defenses only apply once")."""
    stun = body = 0
    for event in session.event_log:
        if event.kind != "ActionResolved":
            continue
        payload = event.result_payload or {}
        if payload.get("lingering_id") == effect.id:
            stun += int(payload.get("defense_absorbed_stun", 0) or 0)
            body += int(payload.get("defense_absorbed_body", 0) or 0)
    return stun, body


def _dose_against_one_defense(session, effect: Lingering, power, *,
                              template, roller, increments_remaining):
    """A dose against what is left of ONE application of his defense.

    6E1 p.332's acid on Hemdring (PD 3/ED 3): 2 BODY, "his armor protects
    him"; then 4, "his armor absorbs one more point ... Hemdring takes the
    remaining 3"; then 3, "takes all of this damage without any defense,
    since his defense was already exceeded". The pool is the defense the
    attack works against (`compute_defense`, so an AVAD's alternate
    defense too): resistant against a Killing attack's BODY, total against
    STUN and against Normal BODY, as for any hit (6E2 p.105). Damage
    Reduction is not reapplied: the page spends the defense, not a share
    of the damage.
    """
    from kirby_combat.adjustments import adjusted_con
    from kirby_combat.models import DiceValues
    from kirby_combat.resolution.damage import compute_damage
    from kirby_combat.resolution.defense import compute_defense
    from kirby_combat.resolution.status import determine_status_changes
    from kirby_combat.session.events import ActionResolved, make_author_combatant
    from kirby_combat.vitals import record_vitals_change

    target = session.combatants[effect.target_id]
    bare = replace(power, constant=False, damage_over_time=None, area=None,
                   side_effects=None)
    count = max(1, int(bare.damage_dice or 0)) + (1 if bare.half_die else 0)
    damage = compute_damage(
        bare, DiceValues(damage=roller.roll_dice(count),
                         stun_multiplier=roller.roll_dice(1)), template)
    defense = compute_defense(target, bare)
    spent_stun, spent_body = _absorbed_so_far(session, effect)
    stun_pool = max(0, int(defense.total_defense) - spent_stun)
    body_def = (defense.resistant_defense if bare.damage_type == "killing"
                else defense.total_defense)
    body_pool = max(0, int(body_def) - spent_body)
    soak_stun = min(int(damage.stun), stun_pool)
    soak_body = min(int(damage.body), body_pool)
    stun = int(damage.stun) - soak_stun
    body = int(damage.body) - soak_body
    if bare.avad and not bare.avad_does_body:
        body = 0                      # 6E1 p.328: AVAD does STUN only
    if stun or body:
        session, _ = record_vitals_change(session, effect.target_id,
                                          stun=-stun, body=-body,
                                          reason="damage")
    status = determine_status_changes(
        stun_before=target.current_stun, stun_after=target.current_stun - stun,
        body_before=target.current_body, body_after=target.current_body - body,
        con=adjusted_con(session, target), max_body=target.max_body,
    )
    return _apply(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(effect.attacker_id),
        declaration_event_id=effect.id,
        result_payload={
            "kind": "attack", "hit": True, "target_id": effect.target_id,
            "power_name": getattr(bare, "name", None),
            "damage_type": bare.damage_type,
            "stun_dealt": stun, "body_dealt": body, "status_changes": status,
            "lingering_id": effect.id,
            "lingering_mode": effect.mode.value,
            "increments_remaining": increments_remaining,
            "defense_absorbed_stun": soak_stun,
            "defense_absorbed_body": soak_body,
            "segment": session.timeline.segment,
        },
    ))


def _attacker_out_since(session, effect: Lingering) -> bool:
    """6E1 p.347: a Constant power "turns off at the end of the Segment
    whenever the character is asleep, Stunned, or Knocked Out"."""
    from kirby_combat.enumeration import is_down
    from kirby_combat.statuses import stunned_or_recovering_for

    attacker = session.combatants.get(effect.attacker_id)
    if attacker is None or is_down(attacker):
        return True
    if stunned_or_recovering_for(session, effect.attacker_id):
        return True
    for event in session.event_log:
        if event.sequence <= effect.applied_seq or event.kind != "ActionResolved":
            continue
        payload = event.result_payload or {}
        if payload.get("target_id") == effect.attacker_id and (
                {"Stunned", "Knocked Out"} & set(payload.get("status_changes") or ())):
            return True
    return False


def _line_of_sight(session, effect: Lingering) -> bool:
    scene = getattr(session, "scene", None)
    if scene is None:
        return True                       # no map: nothing can block it
    positions = getattr(scene, "combatant_positions", None) or {}
    a = positions.get(effect.attacker_id)
    t = positions.get(effect.target_id)
    if a is None or t is None:
        return True
    from kirby_world.geometry import line_of_sight_clear

    return line_of_sight_clear(a, t, getattr(scene, "walls", None) or [])


def _slot_still_on(session, effect: Lingering, power) -> bool:
    framework_id = str(getattr(power, "framework_id", "") or "")
    slot_id = str(getattr(power, "slot_id", "") or "")
    if not framework_id or not slot_id:
        return True
    from kirby_combat.framework import active_slots

    active = active_slots(session, effect.attacker_id, framework_id)
    return not active or slot_id in active


def maintain_constant_attacks(session, actor_id: str, *, template, roller):
    """At the start of the attacker's Phase: pay, then hurt, or let it go.

    6E1 p.130: "The END cost for maintaining Constant Powers is paid when
    the character's Phase begins, before he does anything else." Then the
    target takes the damage, "in every Segment in which the attacker has a
    Phase". Maintaining takes no Action, so the Phase is still his.
    """
    from kirby_combat.actions.recording import _spend_attack_end, _tracks_endurance
    from kirby_combat.endurance import end_cost
    from kirby_combat.enumeration import is_down

    for effect in active_lingering(session, attacker_id=actor_id,
                                   mode=LingeringMode.CONSTANT):
        power = _power_of(session, effect)
        target = session.combatants.get(effect.target_id)
        if power is None:
            session = _end(session, effect.id, LingeringEnd.POWER_NOT_ON_BUILD)
            continue
        if _attacker_out_since(session, effect):
            session = _end(session, effect.id, LingeringEnd.ATTACKER_STUNNED)
            continue
        if target is None or is_down(target):
            session = _end(session, effect.id, LingeringEnd.TARGET_DOWN)
            continue
        if not _line_of_sight(session, effect):
            session = _end(session, effect.id, LingeringEnd.LOST_LINE_OF_SIGHT)
            continue
        if not _slot_still_on(session, effect, power):
            session = _end(session, effect.id, LingeringEnd.SLOT_SWITCHED)
            continue
        attacker = session.combatants[actor_id]
        cost = end_cost(power)
        if cost and _tracks_endurance(template, attacker) and int(
                attacker.state.current_end) < cost:
            # RULING: he stops maintaining rather than burn STUN for END
            # (6E2 p.133 permits it; the engine does not implement it).
            session = _end(session, effect.id, LingeringEnd.NO_END)
            continue
        session = _spend_attack_end(session, attacker, cost, template)
        session = _dose(session, effect, power, template=template,
                        roller=roller, increments_remaining=None)
    return session


def fire_due_doses(session, *, template, roller):
    """Every Damage Over Time dose due by now, in the order it fell due.

    6E1 p.332: "it continues working automatically ... If the caster is
    Stunned or Knocked Out, or loses Line Of Sight on the target, the power
    continues to function as intended." So nothing about the attacker is
    asked --- only the clock.
    """
    now = absolute_segment(session.timeline.turn, session.timeline.segment)
    for effect in active_lingering(session, mode=LingeringMode.DAMAGE_OVER_TIME):
        remaining = int(effect.increments_remaining or 0)
        interval = int(effect.interval_segments or 0)
        given = effect.doses
        power = _power_of(session, effect)
        if power is None:
            session = _end(session, effect.id, LingeringEnd.POWER_NOT_ON_BUILD)
            continue
        while remaining > 0 and effect.applied_at + interval * (given + 1) <= now:
            if effect.target_id not in session.combatants:
                break
            remaining -= 1
            given += 1
            session = _dose(session, effect, power, template=template,
                            roller=roller, increments_remaining=remaining)
        if remaining <= 0:
            session = _end(session, effect.id, LingeringEnd.RAN_ITS_COURSE)
    return session


def resolve_damage_over_time_use(session, attack, template, *, roller,
                                 declaration_event_id, action_type,
                                 combat_type, payload_extras):
    """Use a Damage Over Time power: the Attack Roll, and no damage yet.

    Reached from the attack door. 6E1 p.331: "the first increment of damage
    affects the target one time period after the character uses the
    attack". 6E1 p.332: "A character pays END for a Damage Over Time power
    once, when he uses it." So the roll is made here with every condition
    the door folds onto any other attack (cover, blindness, Dodge, Drained
    CV), the END is paid once, and a hit is written down as a
    `LingeringAttackApplied` for `fire_due_doses` to dose.
    """
    from kirby_combat.actions.recording import (
        _activation_check, _cover_against, _fold_session_cvs,
        _record_failed_activation, _spend_attack_end, apply_side_effects,
    )
    from kirby_combat.endurance import end_cost
    from kirby_combat.models import AttackResult
    from kirby_combat.resolution.to_hit import resolve_to_hit
    from kirby_combat.session.events import (
        ActionDeclared, ActionResolved, make_author_combatant,
    )

    roller = roller or session.dice_roller
    activated = _activation_check(session, attack, roller)
    if activated is not None and not activated["activated"]:
        s, result = _record_failed_activation(
            session, attack, activated,
            declaration_event_id=declaration_event_id, action_type=action_type,
        )
        return apply_side_effects(s, attack, template, roller=roller,
                                  failed=True), result

    folded = _fold_session_cvs(session, attack, combat_type)
    cover_level, cover_ocv = _cover_against(session, folded)
    if cover_ocv:
        folded = replace(folded, ocv_modifier=folded.ocv_modifier + cover_ocv)
    to_hit = resolve_to_hit(folded, template)
    dot = attack.power.damage_over_time
    cost = end_cost(attack.power)
    result = AttackResult(
        hit=to_hit.hit, to_hit=to_hit, damage=None, defense=None,
        stun_dealt=0, body_dealt=0, end_spent=cost, knockback=None,
        status_changes=[], power_xmlid=attack.power.xmlid,
        audit_trail=list(to_hit.audit) + [
            f"Damage Over Time: {dot.increments} increments, one every "
            f"{dot.interval_segments} Segments, the first one interval after "
            "the hit (6E1 p.331)"],
    )

    now = datetime.now(timezone.utc)
    s = session
    attacker_id, target_id = attack.attacker.id, attack.target.id
    decl_id = declaration_event_id
    if decl_id is None:
        declared = ActionDeclared(
            id=str(uuid.uuid4()), session_id=s.id,
            sequence=len(s.event_log) + 1, timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id, action_type=action_type,
            targets=[target_id],
            parameters={"power_xmlid": attack.power.xmlid},
        )
        s = _apply(s, declared)
        decl_id = declared.id
    payload = {
        "kind": action_type, "hit": to_hit.hit,
        "stun_dealt": 0, "body_dealt": 0, "status_changes": [],
        "power_xmlid": attack.power.xmlid,
        "power_source_id": getattr(attack.power, "source_id", None),
        "power_name": getattr(attack.power, "name", None),
        "damage_type": getattr(attack.power, "damage_type", None),
        "is_ranged": bool(getattr(attack.power, "is_ranged", False)),
        "target_id": target_id, "cover_level": cover_level,
        "cover_ocv": cover_ocv, "segment": s.timeline.segment,
        "effective_ocv": to_hit.effective_ocv,
        "target_dcv": to_hit.effective_dcv, "margin": to_hit.margin,
        "damage_over_time": True,
    }
    if activated is not None:
        payload.update({"activated": True, "activation_roll": activated["roll"],
                        "activation_target": activated["target"]})
    if payload_extras is not None:
        payload.update(payload_extras(result))
    s = _apply(s, ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id,
        sequence=len(s.event_log) + 1, timestamp=now,
        author=make_author_combatant(attacker_id),
        declaration_event_id=decl_id, result_payload=payload,
    ))
    s = _spend_attack_end(s, attack.attacker, cost, template)
    s = apply_side_effects(s, attack, template, roller=roller, failed=False)
    if to_hit.hit:
        s = begin_lingering(s, attacker_id=attacker_id, target_id=target_id,
                            power=attack.power)
    return s, result
