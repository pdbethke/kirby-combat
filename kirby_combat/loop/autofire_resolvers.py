"""Autofire bursts: `autofire` (one target, many shots) and `autofire_spray`
(one shot into each of several men along a line).

THE ENGINE NEVER READ AUTOFIRE. 62 attack views in the corpus carry it (42
characters: submachine guns, laser cannons, Flame Barrage, Thornshooting);
every one fired like a single shot, and `power_modifiers` refused the ten
Autofire Areas outright. Rapid Fire was offered with them instead, which 6E2
p.77 forbids: "A character cannot use an Autofire attack as part of a
Multiple Attack sequence unless he knows the Rapid Autofire Skill".

THE BOOK, quoted where it is used:

* 6E2 p.44 (single target): one Attack Roll; "the character hits the target
  one time; in addition, for every full 2 points by which the Attack Roll
  succeeds, he hits the target an additional time", never more than the
  shots fired. `actions/autofire.burst_hits`.
* 6E2 p.44 (multiple targets): the whole line's -1 OCV per 2m on every roll,
  "a separate Attack Roll for each target", "each target can only get hit
  one time", a shot into every 2m of the line, and a miss does not stop the
  rest. `actions/autofire.line_penalty`, `shots_for_line`.
* 6E1 p.329: "A character must pay Endurance (or use up Charges) for each
  shot he takes"; "Each hit from a Autofire attack applies separately
  against the target's defenses"; Knockback is "the BODY of the largest
  attack and add +1 BODY for each additional hit" (6E2 p.116 says the same
  as "+2m for each additional attack that hit").
* 6E2 p.44: "Each Autofire shot counts as a separate attack for purposes of
  determining if the target's Stunned". So each hit is its own pass through
  the attack door.
* 6E2 p.45 (Autofire Area, one target point): "the Attack Roll determines
  how many shots hit the target. The rest are considered misses and have no
  effect"; and "If the attack misses entirely, make one calculation for
  where the shots would scatter to ... then apply the damage from that one
  attack to the affected area."

THE SHAPE, and why. A burst is ONE use of the power --- one Activation Roll
(6E1 p.375), one declaration, one row carrying the power's id and the shots
fired (`charges.spent_charges` counts them) --- and each hit is an
application of that use through `recording.resolve_attack_in_session` with
the roll already made (`AttackInput.fixed_to_hit`) and the use already paid
(`paid_use_event_id`). That is exactly how an Area's victims are hit
(`actions/area_attack.py`), so every hit gets its own defenses, Hit Location,
Stun check and damage application and none of it is copied here. An Autofire
Area's landings are Area uses, each through `area_use` with the burst's roll.

RULINGS, labelled where made:
  * the menu offers the full burst (the most shots the power and its Charges
    allow) and the single shot (the plain `attack` offer, 6E1 p.329: "he can
    always choose to fire fewer shots (even just one shot)"), not every count
    between;
  * the Knockback hit is resolved LAST, so the man is hit by every shot
    before he flies (6E2 p.116: "The Knockback doesn't protect the character
    from being hit by any of the Autofire hits");
  * a spray's line runs nearest-first from the shooter (6E2 p.44 lets the
    attacker choose; nothing on the menu says how).

NOT BUILT, so not offered (`autofire_offers.py`): an Autofire spray of an
Area over several target points (6E1 p.321), hand-to-hand Autofire (a
Block of it is one roll that stops some of the hits, 6E2 p.59, and the door
rolls a Block per hit), Autofire at objects (the construct door makes no
Attack Roll, so it has no margin to count hits by), Autofire Skills.
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import (
    ResolvedAction, UnresolvableAction, _events_since, resolves,
)

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate

AUTOFIRE = "autofire"
AUTOFIRE_SPRAY = "autofire_spray"


def offered_shots(action: LegalAction) -> int:
    """The shots the OFFER named, from its action_id tail. An offer that
    does not say is not one this module made."""
    tail = (action.action_id or "").rsplit(":", 1)[-1]
    if not tail.isdigit() or int(tail) < 1:
        raise UnresolvableAction(action.kind, action.action_id)
    return int(tail)


def _now():
    return datetime.now(timezone.utc)


def _attack_input(session, actor, target, power, roller, template, *, ocv_modifier: int):
    """The burst's `AttackInput`, built the way `_resolve_attack` builds a
    single shot's: the Set, the Grab and the bodies in the way."""
    from kirby_combat.loop.resolvers import (
        _attack_dice, _grab_cv, _melee_cover, _range_to, _set_bonus,
        _with_half_die,
    )
    from kirby_combat.models import AttackInput

    grab = _grab_cv(session, actor, target)
    return AttackInput(
        attacker=actor, target=target, power=power,
        distance_m=_range_to(session, actor, target), aim=None,
        dice=_attack_dice(roller, _with_half_die(power, max(1, int(power.damage_dice)))),
        ocv_modifier=_set_bonus(session, actor, target) + grab.ocv_delta + ocv_modifier,
        grab_ocv_factor=grab.ocv_factor, grab_dcv_factor=grab.dcv_factor,
        melee_cover_ocv=_melee_cover(session, actor, target, template).ocv_penalty,
    )


def _burst_roll(session, attack, template):
    """The ONE Attack Roll, with every condition the door folds (6E2 p.44:
    "a normal Attack Roll"): `_fold_session_cvs`, then cover, in the door's
    own order."""
    from kirby_combat.actions.recording import _cover_against, _fold_session_cvs
    from kirby_combat.resolution.to_hit import resolve_to_hit

    folded = _fold_session_cvs(session, attack, None)
    _, cover_ocv = _cover_against(session, folded)
    if cover_ocv:
        folded = replace(folded, ocv_modifier=folded.ocv_modifier + cover_ocv)
    return resolve_to_hit(folded, template)


def _hits(to_hit, shots: int) -> int:
    """6E2 p.44's count. A roll that hits on a 3 (6E2 p.37) with a negative
    margin still hits once."""
    from kirby_combat.actions.autofire import burst_hits

    if not to_hit.hit:
        return 0
    return burst_hits(max(0, int(to_hit.margin)), shots)


def _failed_activation(session, attack, activated, template, roller, kind):
    from kirby_combat.actions.recording import (
        _record_failed_activation, apply_side_effects,
    )

    s, result = _record_failed_activation(
        session, attack, activated, declaration_event_id=None, action_type=kind)
    return apply_side_effects(s, attack, template, roller=roller, failed=True), result


def _declare(session, actor, kind: str, targets: list[str], power, shots: int):
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ActionDeclared, make_author_combatant

    declared = ActionDeclared(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=_now(),
        author=make_author_combatant(actor.id), combatant_id=actor.id,
        action_type=kind, targets=list(targets),
        parameters={"power_xmlid": power.xmlid, "autofire_shots": shots},
    )
    return apply_event(session, declared), declared.id


def _use_row(session, actor, decl_id: str, payload: dict):
    """The use: the row that carries the power's id and the shots fired, so
    `charges.spent_charges` counts every shot (6E1 p.329)."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ActionResolved, make_author_combatant

    use = ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=_now(),
        author=make_author_combatant(actor.id), declaration_event_id=decl_id,
        result_payload={"stun_dealt": 0, "body_dealt": 0, "status_changes": [],
                        "segment": session.timeline.segment, **payload},
    )
    return apply_event(session, use), use


def _power_fields(power) -> dict:
    return {"power_xmlid": power.xmlid,
            "power_source_id": getattr(power, "source_id", None),
            "power_name": getattr(power, "name", None)}


def _pay(session, actor, power, shots: int, template):
    """END for each shot taken (6E1 p.329)."""
    from kirby_combat.actions.recording import _spend_attack_end
    from kirby_combat.endurance import end_cost

    return _spend_attack_end(session, actor, end_cost(power) * shots, template,
                             power=power)


def _knockback_order(power, dice_per_hit: list, template) -> list[tuple[Any, bool]]:
    """Each hit's dice, with the one that carries the burst's Knockback last.

    6E1 p.329: "use the BODY of the largest attack" --- BODY ROLLED, as for
    any Knockback (6E2 p.116), so it is read off the dice before anyone's
    defenses, by the same `compute_damage` the door uses.
    """
    from kirby_combat.resolution.damage import compute_damage

    if not dice_per_hit:
        return []
    bodies = [compute_damage(power, d, template).body for d in dice_per_hit]
    largest = max(range(len(bodies)), key=lambda i: (bodies[i], -i))
    rest = [(d, False) for i, d in enumerate(dice_per_hit) if i != largest]
    return rest + [(dice_per_hit[largest], True)]


def _hit_attack(base, dice, to_hit, *, carries_knockback: bool, hits: int):
    power = base.power if carries_knockback else replace(base.power, no_knockback=True)
    return replace(base, power=power, dice=replace(dice, to_hit=base.dice.to_hit),
                   fixed_to_hit=to_hit,
                   knockback_body_bonus=(hits - 1) if carries_knockback else 0)


@resolves(AUTOFIRE)
def _resolve_autofire(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """A burst at one man (6E2 p.44), or at one target point (p.45)."""
    from kirby_combat.actions.recording import (
        _activation_check, apply_side_effects, resolve_attack_in_session,
    )
    from kirby_combat.loop.resolvers import _attack_dice, _with_half_die

    power = action._attack_view
    target = session.combatants.get(action.target_id)
    if power is None or getattr(power, "autofire", None) is None or target is None:
        raise UnresolvableAction(action.kind, action.action_id)
    shots = offered_shots(action)
    if shots > power.autofire.shots:
        raise UnresolvableAction(action.kind, action.action_id)

    base = _attack_input(session, actor, target, power, roller, template, ocv_modifier=0)
    activated = _activation_check(session, base, roller)
    if activated is not None and not activated["activated"]:
        s, result = _failed_activation(session, base, activated, template, roller, AUTOFIRE)
        return ResolvedAction(session=s, kind=action.kind, action_id=action.action_id,
                              result=[result], events=_events_since(session, s))
    if getattr(power, "area", None) is not None:
        return _area_burst(session, actor, action, base, shots,
                           template=template, roller=roller)

    to_hit = _burst_roll(session, base, template)
    hits = _hits(to_hit, shots)
    s, decl_id = _declare(session, actor, AUTOFIRE, [target.id], power, shots)
    s, use = _use_row(s, actor, decl_id, {
        "kind": AUTOFIRE, "autofire_use": True, "target_id": target.id,
        "hit": to_hit.hit, "hits": hits, "shots_fired": shots,
        "roll": to_hit.roll, "target_number": to_hit.target_number,
        "effective_ocv": to_hit.effective_ocv, "target_dcv": to_hit.effective_dcv,
        "margin": to_hit.margin, **_power_fields(power),
    })
    s = _pay(s, actor, power, shots, template)
    s = apply_side_effects(s, base, template, roller=roller, failed=False)

    dice = [_attack_dice(roller, _with_half_die(power, max(1, int(power.damage_dice))))
            for _ in range(hits)]
    results = []
    plan = _knockback_order(power, dice, template) or [(base.dice, False)]
    for shot, (d, carries) in enumerate(plan, start=1):
        s, result = resolve_attack_in_session(
            s, _hit_attack(base, d, to_hit, carries_knockback=carries, hits=hits),
            template, declaration_event_id=decl_id, action_type=AUTOFIRE,
            roller=roller,
            payload_extras=lambda _r, shot=shot: {"autofire_use_id": use.id,
                                                  "autofire_shot": shot},
            paid_use_event_id=use.id,
        )
        results.append(result)
    return ResolvedAction(session=s, kind=action.kind, action_id=action.action_id,
                          result=results, events=_events_since(session, s))


def _area_burst(session, actor, action: LegalAction, base, shots: int, *,
                template, roller) -> ResolvedAction:
    """6E2 p.45: an Autofire Area at one target point. The roll says how
    many land; each landing is an Area use with its own damage roll; the
    rest are misses with no effect, and a total miss scatters once."""
    from kirby_combat.actions.area_attack import area_attack_roll
    from kirby_combat.actions.recording import resolve_attack_in_session
    from kirby_combat.loop.resolvers import _attack_dice, _with_half_die

    power = base.power
    to_hit = area_attack_roll(session, base, template)
    hits = _hits(to_hit, shots)
    landings = max(1, hits)              # a total miss still lands, scattered
    s, decl_id = _declare(session, actor, AUTOFIRE, [action.target_id], power, shots)
    dice = [_attack_dice(roller, _with_half_die(power, max(1, int(power.damage_dice))))
            for _ in range(landings)]
    results = []
    plan = _knockback_order(power, dice, template) if hits else [(dice[0], True)]
    for shot, (d, carries) in enumerate(plan, start=1):
        s, result = resolve_attack_in_session(
            s, _hit_attack(base, d, to_hit, carries_knockback=carries, hits=max(1, hits)),
            template, declaration_event_id=decl_id, action_type=AUTOFIRE,
            roller=roller,
            payload_extras=lambda _r, shot=shot: {"autofire_shot": shot},
        )
        results.append(result)
    missed = shots - landings
    if missed:
        # The shots that went nowhere still cost END and Charges (6E1 p.329).
        s, _ = _use_row(s, actor, decl_id, {
            "kind": AUTOFIRE, "autofire_misses": True, "target_id": action.target_id,
            "hit": False, "shots_fired": missed, **_power_fields(power),
        })
        s = _pay(s, actor, power, missed, template)
    return ResolvedAction(session=s, kind=action.kind, action_id=action.action_id,
                          result=results, events=_events_since(session, s))


def spray_line_m(session, target_ids) -> float | None:
    """The metres of line 'connecting' the targets in order (6E2 p.44), or
    None when the map cannot say."""
    import math

    positions = getattr(getattr(session, "scene", None), "combatant_positions", None) or {}
    points = [positions.get(t) for t in target_ids]
    if any(p is None for p in points):
        return None
    return sum(math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))
               for a, b in zip(points, points[1:]))


@resolves(AUTOFIRE_SPRAY)
def _resolve_autofire_spray(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """One shot at each man along a line, each its own roll at the whole
    line's penalty (6E2 p.44)."""
    from kirby_combat.actions.autofire import line_penalty, shots_for_line
    from kirby_combat.actions.recording import (
        _activation_check, apply_side_effects, resolve_attack_in_session,
    )

    power = action._attack_view
    ids = list(action.target_ids or ())
    if (power is None or getattr(power, "autofire", None) is None or len(ids) < 2
            or any(t not in session.combatants for t in ids)
            or getattr(power, "area", None) is not None):
        raise UnresolvableAction(action.kind, action.action_id)
    shots = offered_shots(action)
    line_m = spray_line_m(session, ids)
    if (line_m is None or shots > power.autofire.shots
            or shots_for_line(len(ids), line_m) > shots):
        raise UnresolvableAction(action.kind, action.action_id)
    penalty = line_penalty(line_m)

    first = session.combatants[ids[0]]
    probe = _attack_input(session, actor, first, power, roller, template,
                          ocv_modifier=penalty)
    activated = _activation_check(session, probe, roller)
    if activated is not None and not activated["activated"]:
        s, result = _failed_activation(session, probe, activated, template, roller,
                                       AUTOFIRE_SPRAY)
        return ResolvedAction(session=s, kind=action.kind, action_id=action.action_id,
                              result=[result], events=_events_since(session, s))

    s, decl_id = _declare(session, actor, AUTOFIRE_SPRAY, ids, power, shots)
    s, use = _use_row(s, actor, decl_id, {
        "kind": AUTOFIRE_SPRAY, "autofire_use": True, "target_ids": ids,
        "target_id": ids[0], "shots_fired": shots, "line_m": round(line_m, 2),
        "line_penalty": penalty, **_power_fields(power),
    })
    s = _pay(s, actor, power, shots, template)
    s = apply_side_effects(s, probe, template, roller=roller, failed=False)
    results = []
    for shot, tid in enumerate(ids, start=1):
        target = s.combatants[tid]
        attack = (probe if shot == 1 else
                  _attack_input(s, actor, target, power, roller, template,
                                ocv_modifier=penalty))
        s, result = resolve_attack_in_session(
            s, attack, template, declaration_event_id=decl_id,
            action_type=AUTOFIRE_SPRAY, roller=roller,
            payload_extras=lambda _r, shot=shot: {"autofire_use_id": use.id,
                                                  "autofire_shot": shot},
            paid_use_event_id=use.id,
        )
        results.append((tid, result))
    return ResolvedAction(session=s, kind=action.kind, action_id=action.action_id,
                          result=results, events=_events_since(session, s))
