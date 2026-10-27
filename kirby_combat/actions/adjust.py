"""Using an Aid, a Drain or a Healing on someone (6E1 p.169, p.197, p.234).

The resolvers in `loop/resolvers.py` delegate here; the rule lives in one
place and the registry keeps its one-line doors.

THE CONSUMER'S OLD DRIVER (deleted in kirby-api 70ad60f) is where this was
ported from, and it was wrong in ways this corrects:

- it fell back to STR when the power named something it did not parse
  (`_AID_STAT_DEFAULT`, `_DRAIN_STAT_DEFAULT`). 6E1 p.137: "A character must
  specify exactly which of a character's Characteristics or Powers he's
  affecting". A power naming what this engine cannot adjust is NOT OFFERED;
- it applied the dice total as POINTS of the stat. 6E1 p.137 divides by the
  characteristic's cost per point, and p.143 halves the effect against a
  defensive one;
- it rolled no Attack Roll for a Drain (6E1 p.197) and subtracted no Power
  Defense;
- its Aid had no maximum effect (6E1 p.169) and also added the roll to the
  target's current STUN whatever was being Aided;
- its Healing restored the roll as STUN and a quarter of it as BODY, "as a
  heuristic". 6E1 p.234 heals the Characteristic the power is bought for,
  never above its starting value, at half effect for BODY and STUN (p.143;
  the p.234 example: "Healing BODY 2d6 spell (maximum effect 12 points, or
  6 BODY)"), and only by the margin over earlier rolls (p.234).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from kirby_combat.adjustments import (
    AdjustedCharacteristic, AdjustedPower, characteristic_targets, cost_per_die,
    cost_per_point, expendable_vital, halved_for, live_adjustments,
    maximum_effect, points_for, power_targets_on, roll_effect,
)

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


AID = "aid"
DRAIN = "drain"
HEAL = "heal"


# ---------------------------------------------------------------------------
# What an offer names
# ---------------------------------------------------------------------------

def power_action_suffix(target: AdjustedPower) -> str:
    """The tail an offer's action_id carries when it names one of the
    target's powers (6E1 p.137: "he has to specify exactly which Blast")."""
    return f"power={target.source_id}"


def targets_for(action, power, target) -> tuple:
    """What this offer adjusts on ``target``: its characteristics, or the
    one power the action_id names. Raises when it names neither --- an
    offer enumeration could not have written."""
    chars = characteristic_targets(power)
    if chars is not None:
        return chars
    tail = action.action_id.rsplit(":", 1)[-1]
    if tail.startswith("power="):
        wanted = tail[len("power="):]
        for candidate in power_targets_on(power, target):
            if candidate.source_id == wanted:
                return (candidate,)
    raise ValueError(
        f"{action.action_id!r} names nothing {getattr(power, 'name', power)!r} "
        f"can adjust on {target.id!r}"
    )


def is_ranged(power) -> bool:
    """6E1 p.169 (Aid) and p.234 (Healing) are No Range; p.197's Drain is
    "10m x Base Points". The cost engine says which, Ranged Advantage
    included, and gives the distance."""
    return str(getattr(power, "range", "") or "").strip().lower() == "yes"


def range_m(power) -> float:
    return float(getattr(power, "range_value", 0) or 0) if is_ranged(power) else 0.0


# ---------------------------------------------------------------------------
# The Attack Roll
# ---------------------------------------------------------------------------

def _attack_view(power):
    """The power as the to-hit door wants it: an `AttackPower` with no
    damage dice, its range and its identity."""
    from kirby_combat.hero_view import _has_modifier
    from kirby_combat.models import AttackPower

    reach = range_m(power)
    return AttackPower(
        xmlid=(getattr(power, "xmlid", "") or "").upper(),
        name=getattr(power, "name", None) or getattr(power, "alias", "") or "",
        damage_dice=0, half_die=False, plus_one=False, damage_type="normal",
        defense_type="power", range_m=reach, uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        no_range_modifier=_has_modifier(power, "NORANGEMODIFIER"),
        active_points=int(float(getattr(power, "active_cost", 0) or 0)),
        is_ranged=reach > 0, source_id=str(getattr(power, "id", "") or ""),
    )


def attack_roll(session: "CombatSession", actor, target, power, roller, template):
    """6E1 p.197: "To use Drain, a character must make an Attack Roll" ---
    against DCV, with every condition of the fight on both CVs, through the
    same door every attack takes (`recording._fold_session_cvs`)."""
    from kirby_combat.actions.recording import _fold_session_cvs
    from kirby_combat.models import AttackInput, DiceValues
    from kirby_combat.resolution.to_hit import resolve_to_hit
    from kirby_world.geometry import distance_3d
    from kirby_world.occupancy import position_of

    distance = None
    if session.scene is not None:
        here = position_of(session.scene, actor.id)
        there = position_of(session.scene, target.id)
        if here is not None and there is not None:
            distance = distance_3d(here, there)
    attack = _fold_session_cvs(session, AttackInput(
        attacker=actor, target=target, power=_attack_view(power),
        distance_m=distance, aim=None, dice=DiceValues(to_hit=roller.roll_dice(3)),
    ))
    return resolve_to_hit(attack, template)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _vitals(session, actor_id: str, target_id: str, vital: str, amount: int, reason: str):
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import VitalsChanged, make_author_combatant

    if not amount:
        return session
    return apply_event(session, VitalsChanged(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=_now(),
        author=make_author_combatant(actor_id), combatant_id=target_id,
        reason=reason, **{vital: int(amount)},
    ))


def _live_cp(session, target_id: str, stat: str) -> int:
    return sum(a.character_points for a in live_adjustments(session, target_id)
               if a.stat == stat)


def _per_point(target, adjusted) -> float:
    if isinstance(adjusted, AdjustedCharacteristic):
        return cost_per_point(target, adjusted.xmlid)
    attack = next(a for a in target.attacks if str(a.source_id) == adjusted.source_id)
    return cost_per_die(attack)


def apply_adjustment(
    session: "CombatSession", actor_id: str, target_id: str, adjusted,
    character_points: int, *, fade_rate_per_turn: int,
) -> tuple["CombatSession", int]:
    """Record ``character_points`` (signed) on one stat of the target, and
    move the current value of an expendable one with it.

    6E1 p.138, Decreasing Expendable Abilities: a Drain "affects both the
    current total of that Characteristic and the maximum"; an Aid to STUN or
    END adds to what he has now (p.169's Gigawatt "gaining 10 STUN and 20
    END"). Returns the session and the points of the stat that moved.
    """
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import AdjustmentApplied, make_author_combatant

    target = session.combatants[target_id]
    per_point = _per_point(target, adjusted)
    before = points_for(_live_cp(session, target_id, adjusted.stat), per_point)
    session = apply_event(session, AdjustmentApplied(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=_now(),
        author=make_author_combatant(actor_id), target_id=target_id,
        stat=adjusted.stat, delta=int(character_points),
        fade_rate_per_turn=int(fade_rate_per_turn), cost_per_point=per_point,
    ))
    after = points_for(_live_cp(session, target_id, adjusted.stat), per_point)
    moved = after - before
    if isinstance(adjusted, AdjustedCharacteristic):
        vital = expendable_vital(adjusted.xmlid)
        if vital is not None:
            session = _vitals(session, actor_id, target_id, vital, moved,
                              reason="drain" if moved < 0 else "aid")
    return session, moved


#: 6E1 p.141: "The Character Points gained or lost via an Adjustment Power
#: (except Healing) fade/return at the rate of 5 Character Points per Turn."
#: Delayed Return Rate (6E1 p.142) moves it down the Time Chart, which this
#: engine's Turn-granular fade cannot express; a power bought with it is
#: recorded at the standard rate and SAYS SO in its payload.
STANDARD_FADE_PER_TURN = 5


def _record(session, actor, action, payload: dict):
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import (
        ActionDeclared, ActionResolved, make_author_combatant,
    )

    declared = ActionDeclared(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=_now(),
        author=make_author_combatant(actor.id), combatant_id=actor.id,
        action_type=action.kind,
        targets=[action.target_id] if action.target_id else [], parameters={},
    )
    session = apply_event(session, declared)
    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=_now(),
        author=make_author_combatant(actor.id),
        declaration_event_id=declared.id, result_payload=payload,
    ))


# ---------------------------------------------------------------------------
# Aid and Drain
# ---------------------------------------------------------------------------

def resolve_aid_or_drain(session, actor, action, *, which: str, roller, template):
    """Aid (6E1 p.169) or Drain (6E1 p.197). Returns (session, payload)."""
    from kirby_combat.hero_view import _has_modifier

    if action.target_id is None:
        raise ValueError(f"{action.action_id!r}: an Adjustment names its target")
    power = action._attack_view
    target = session.combatants[action.target_id]
    adjusted = targets_for(action, power, target)

    payload: dict = {
        "kind": action.kind, "target_id": target.id,
        "power_source_id": str(getattr(power, "id", "") or ""),
        "stats": [a.stat for a in adjusted],
        "delayed_return_rate_not_modelled": _has_modifier(power, "DELAYEDRETURNRATE"),
    }
    if which == DRAIN:
        to_hit = attack_roll(session, actor, target, power, roller, template)
        payload.update(hit=to_hit.hit, roll=to_hit.roll,
                       target_number=to_hit.target_number)
        if not to_hit.hit:
            return _record(session, actor, action, payload), payload
    else:
        # 6E1 p.169: "If the target's willing to be affected by the Aid,
        # including when the character uses his Aid on himself, the Attack
        # Roll succeeds automatically". Aid is offered only on the actor
        # and his own side.
        payload.update(hit=True)

    rolled = roll_effect(power, roller)
    payload["rolled"] = rolled
    if which == DRAIN:
        # "then subtracts the target's Power Defense (if any)" (p.197).
        power_defense = int(target.combat_stats().power_defense)
        rolled = max(0, rolled - power_defense)
        payload["power_defense"] = power_defense

    # Everything decided BEFORE anything is written, so the resolution row
    # says what happened and is never edited after it is on the log.
    planned: list[tuple] = []
    for element in adjusted:
        points = halved_for(element, rolled)
        already = _live_cp(session, target.id, element.stat)
        if which == AID:
            # MAXIMUM EFFECT (6E1 p.169, p.138): what is already Aided on this
            # stat counts against it, "the largest maximum for any of the
            # Powers used" -- which, for one power, is this one's.
            cap = halved_for(element, maximum_effect(power))
            signed = max(0, min(points, cap - max(0, already)))
        else:
            # "There's no limit to the amount of Character Points a character
            # can Drain" (p.197); the stat floors at 0 where it is read.
            signed = -points
        per_point = _per_point(target, element)
        moved = points_for(already + signed, per_point) - points_for(already, per_point)
        planned.append((element, signed, moved))
    payload["character_points"] = {e.stat: cp for e, cp, _ in planned}
    payload["points_moved"] = {e.stat: m for e, _, m in planned}

    session = _record(session, actor, action, dict(payload))
    for element, signed, _ in planned:
        if signed:
            session, _ = apply_adjustment(
                session, actor.id, target.id, element, signed,
                fade_rate_per_turn=STANDARD_FADE_PER_TURN,
            )
    return session, payload


# ---------------------------------------------------------------------------
# Healing
# ---------------------------------------------------------------------------

#: What HD writes in a Healing's INPUT for 6E1 p.236's Simplified Healing:
#: "The total on the Healing dice Heals STUN damage, and the Normal Damage
#: BODY on the Healing dice Heals BODY damage."
_SIMPLIFIED = frozenset({"SIMPLIFIED", "SIMPLIFIED HEALING"})


def is_simplified(power) -> bool:
    return (getattr(power, "input", None) or "").strip().upper() in _SIMPLIFIED


def healing_targets(power) -> tuple[AdjustedCharacteristic, ...] | None:
    """What a Healing restores, or None when it is not built here.

    The expendable characteristics only --- BODY, STUN and END, the ones a
    fight takes away. Healing a Drained characteristic back (6E1 p.234:
    "restore Characteristics and Powers that have been lost or reduced by
    any cause") is NOT BUILT: it would have to cancel a Drain's points out of
    the log, and nothing in the corpus buys it (35 Healing BODY, 17
    Simplified, 1 STUN, 1 BODY and END).
    """
    if is_simplified(power):
        return (AdjustedCharacteristic("STUN"), AdjustedCharacteristic("BODY"))
    chars = characteristic_targets(power)
    if chars is None or any(expendable_vital(c.xmlid) is None for c in chars):
        return None
    return chars


def _best_prior_roll(session, target_id: str, stat: str) -> int:
    """6E1 p.234, Repeated Healing: within a Day, a later Healing "has to roll
    more than [the earlier roll] to Heal [him] further, and can only Heal him
    to the extent his roll exceeds" it --- whoever made the earlier one
    (Brother Willem against Brother Herbert's 4). A fight is shorter than a
    Day, so every earlier Healing of this stat in it counts."""
    best = 0
    for evt in session.event_log:
        if getattr(evt, "kind", None) != "ActionResolved":
            continue
        p = getattr(evt, "result_payload", None) or {}
        if p.get("kind") == HEAL and p.get("target_id") == target_id:
            best = max(best, int((p.get("rolled_by_stat") or {}).get(stat, 0)))
    return best


def resolve_heal(session, actor, action, *, roller, template):
    """Healing (6E1 p.234). Returns (session, payload).

    "Using Healing constitutes an Attack Action and requires an Attack Roll.
    The GM may dispense with the Attack Roll in the case of a willing
    subject" --- RULING: dispensed with, since it is offered only on the
    healer and his own side. "Healing cannot boost Characteristics or Powers
    above their starting values", and "The points gained from Healing do not
    fade", so it is a `VitalsChanged`, never an `AdjustmentApplied`.
    """
    from kirby_combat.resolution.damage import _body_for_normal_die, half_die_face
    from kirby_combat.adjustments import effect_dice

    if action.target_id is None:
        raise ValueError(f"{action.action_id!r}: a Healing names its target")
    power = action._attack_view
    target = session.combatants[action.target_id]
    targets = healing_targets(power)
    if targets is None:
        raise ValueError(f"{action.action_id!r}: this Healing is not built")

    full, half, pips = effect_dice(power)
    dice = roller.roll_dice(full + (1 if half else 0))
    total = max(0, sum(dice[:full]) + (half_die_face(dice[-1]) if half else 0) + pips)

    # Per stat, the CHARACTER POINTS rolled (before the margin rule) and the
    # points of the stat they buy.
    if is_simplified(power):
        # 6E1 p.236: the total heals STUN; the dice "counted like Normal
        # Damage BODY" heal BODY. Simplified Healing restores those directly
        # --- the example heals "20 STUN and 6 BODY" off a 20 --- so no
        # halving. Its ½d6 counts BODY as 6E2 p.100's does.
        from kirby_combat.resolution.damage import half_die_body

        body = sum(_body_for_normal_die(v) for v in dice[:full]) + (
            half_die_body(dice[-1]) if half else 0)
        rolled_by_stat = {"STUN": total, "BODY": body}
        per_point = {"STUN": 1.0, "BODY": 1.0}
        halving = False
    else:
        rolled_by_stat = {t.stat: total for t in targets}
        per_point = {t.stat: cost_per_point(target, t.xmlid) for t in targets}
        halving = True

    margins = {
        stat: max(0, rolled - _best_prior_roll(session, target.id, stat))
        for stat, rolled in rolled_by_stat.items()
    }
    stats = target.combat_stats()
    maxima = {"STUN": stats.max_stun, "BODY": stats.max_body, "END": stats.max_end}
    healed: dict[str, int] = {}
    for element in targets:
        cp = margins[element.stat]
        if halving:
            cp = halved_for(element, cp)
        points = points_for(cp, per_point[element.stat])
        vital = expendable_vital(element.xmlid)
        current = int(getattr(target.state, f"current_{vital}"))
        healed[element.stat] = max(0, min(points, int(maxima[element.xmlid]) - current))

    payload: dict = {
        "kind": action.kind, "target_id": target.id, "hit": True,
        "power_source_id": str(getattr(power, "id", "") or ""),
        "rolled": total, "rolled_by_stat": dict(rolled_by_stat),
        "healed": dict(healed),
    }
    session = _record(session, actor, action, dict(payload))
    for element in targets:
        session = _vitals(session, actor.id, target.id,
                          expendable_vital(element.xmlid), healed[element.stat],
                          reason="healing")
    return session, payload
