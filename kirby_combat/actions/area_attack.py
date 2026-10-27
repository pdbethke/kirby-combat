"""An Area Of Effect attack --- everyone in the area, from one Attack Roll.

6E1 p.321: "To use an Area Of Effect power, a character targets the center
of the area on a target point (which has DCV 3). Then he makes an Attack
Roll with any modifiers that apply (including the Range Modifier)." And:
"An Area Of Effect power affects all the characters in the area ... the
character rolls damage once and each victim takes that damage (he doesn't
roll once per victim)."

WHAT THE DELETED DRIVER DID, AND WHY THIS IS NOT A PORT OF IT. kirby-api's
`_resolve_multiple_attack(kind_label="attack_aoe")` hit EVERY LIVING ENEMY
in the fight, wherever they stood, with a separate Attack Roll each at a
cumulative -2 OCV (Multiple Attack's arithmetic), a separate damage roll
each, and none of its own side. Every one of those is the opposite of the
page: the area is a place, not a roster; one roll, not many; one damage
roll, not many; and the attacker's friends in it are hit too. What it got
right --- the template catching constructs, anchored on the hex of the man
the chooser named --- is kept.

THE ONE DOOR. This is reached from `recording.resolve_attack_in_session`,
the door every attack in the engine takes, so a move-and-strike, a Pushed
blast and a Haymaker with an Area power are area attacks too. Each victim's
damage goes back through that same door with the Attack Roll already made
(`AttackInput.fixed_to_hit`) and the use already paid for, so every victim
gets his own defenses, Hit Location, Stun and Knockback exactly as a man
shot on his own would.

RULINGS, labelled where they are made:
  * no map: the area holds the named target and nobody else, because
    nothing can be shown to stand beside him;
  * the miss direction (6E2 p.42's d6 diagram is a picture the text does
    not reproduce): 1 = long, past the target point, then 60 degrees
    clockwise per pip;
  * Selective hits the attacker's enemies --- "he can ignore 'friendlies'"
    --- and no constructs; Nonselective rolls against every character;
    neither attacks a construct, because 6E1 p.326's further rolls are "at
    that target's normal DCV" and the engine has no ruling on a wall's.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from kirby_combat.power_modifiers import AreaShape, AreaSpec, AreaTargeting

if TYPE_CHECKING:
    from kirby_combat.models import AttackInput, AttackResult
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate


#: 6E2 p.42: "the DCV of a target point is 3, or 0 if the target point is
#: adjacent to the attacker (i.e., within 2m)".
TARGET_POINT_DCV = 3
ADJACENT_TARGET_POINT_DCV = 0
ADJACENT_M = 2.0
#: 6E2 p.42: "misses the target point by 2m for every 1 point which the
#: Attack Roll fails by; the maximum miss distance is half the distance to
#: the target".
MISS_M_PER_POINT = 2.0
#: 6E1 p.322: "a 60 degree cone"; a Thin Cone "only covers a 30 degree cone".
CONE_HALF_ANGLE_RAD = math.radians(30)
THIN_CONE_HALF_ANGLE_RAD = math.radians(15)
#: 6E1 p.325: "the full effect of the base power occurs at the target point
#: and 2m beyond that ... decreases by one Damage Class ... for every 2m".
EXPLOSION_FULL_M = 2.0
EXPLOSION_STEP_M = 2.0


@dataclass(frozen=True)
class _TargetPoint:
    """The thing an Area's Attack Roll is made against: a point, DCV 3."""

    dcv: int
    id: str = "target-point"


@dataclass(frozen=True)
class AreaGeometry:
    """Where the area lies: its target point and the direction it opens."""

    point: tuple[float, float, float]
    #: Unit vector, attacker toward the target point, in xy. Cones and Lines
    #: open along it (6E1 p.322: a Cone "must have one of its angles
    #: pointing directly at the character").
    axis: tuple[float, float]


def is_area_attack(power: Any) -> bool:
    return getattr(power, "area", None) is not None


def _position(session, combatant_id):
    scene = getattr(session, "scene", None)
    if scene is None:
        return None
    return (getattr(scene, "combatant_positions", None) or {}).get(combatant_id)


def _xyz(p) -> tuple[float, float, float]:
    return (float(p.x), float(p.y), float(getattr(p, "z", 0.0) or 0.0))


def _no_range(power) -> bool:
    return not getattr(power, "is_ranged", False)


def _axis(frm, to) -> tuple[float, float]:
    dx, dy = to[0] - frm[0], to[1] - frm[1]
    length = math.hypot(dx, dy)
    if length == 0.0:
        return (1.0, 0.0)
    return (dx / length, dy / length)


def _deviate(point, shooter, missed_by: int, roll: int):
    """6E2 p.42's miss: 2m per point missed, at most half the distance to the
    target, in a d6 direction (1 = long, then 60 degrees clockwise --- the
    RULING in the module docstring)."""
    full = math.dist(point[:2], shooter[:2])
    distance = min(MISS_M_PER_POINT * missed_by, full / 2.0)
    base = math.atan2(point[1] - shooter[1], point[0] - shooter[0])
    angle = base - math.radians(60) * (roll - 1)
    return (point[0] + distance * math.cos(angle),
            point[1] + distance * math.sin(angle), point[2]), distance


def _in_area(spec: AreaSpec, geo: AreaGeometry, here) -> tuple[bool, float]:
    """Whether a point is inside the area, and its distance from the target
    point (which an Explosion reads)."""
    px, py, pz = geo.point
    dist2d = math.hypot(here[0] - px, here[1] - py)
    if spec.shape is AreaShape.RADIUS:
        # 6E1 p.322: "An Area Of Effect (Radius) is spherical".
        d = math.dist(here, geo.point)
        return d <= spec.size_m, d
    along = (here[0] - px) * geo.axis[0] + (here[1] - py) * geo.axis[1]
    if spec.shape is AreaShape.CONE:
        if dist2d > spec.size_m or along < 0:
            return (dist2d == 0.0), dist2d
        if dist2d == 0.0:
            return True, 0.0
        half = THIN_CONE_HALF_ANGLE_RAD if spec.thin_cone else CONE_HALF_ANGLE_RAD
        return math.acos(max(-1.0, min(1.0, along / dist2d))) <= half, dist2d
    if spec.shape is AreaShape.LINE:
        across = abs(-(here[0] - px) * geo.axis[1] + (here[1] - py) * geo.axis[0])
        inside = (0.0 <= along <= spec.size_m and across <= spec.width_m / 2.0
                  and abs(here[2] - pz) <= spec.height_m)
        return inside, max(0.0, along)
    raise ValueError(f"area shape {spec.shape!r} is not resolvable; it should "
                     "not have been offered")


#: 6E1 p.325, Killing Attacks: "subtract one die, starting with the highest
#: die, for every 6m of expansion (full dice within 6m of the target point,
#: -1 die for the next 6m, and so on)".
KILLING_EXPLOSION_STEP_M = 6.0


def explosion_dice_lost(distance_m: float, *, killing: bool) -> int:
    """Dice an Explosion has lost this far from the target point.

    6E1 p.325: full effect "at the target point and 2m beyond that", then
    one DC "for every 2m". The book's own example: Kasdrevan's 8d6, "someone
    5m away from the target point would take the same damage, less the two
    sixes" --- two dice at 5m.

    A Killing die is three Damage Classes, and the page gives the GM two
    methods for it: a die per 6m, or 2 points of damage per 2m. RULING,
    labelled: the first, because it is the same arithmetic as every other
    Explosion --- whole dice, largest first --- on a 6m step, and the second
    would reach into the BODY total after the dice are read. The page's
    own Arkelos example (4d6 RKA, 8m Radius) shows the GM ruling a third
    way for an area too small to diminish fully; this engine does not
    resize a step to the area bought.
    """
    full_m = KILLING_EXPLOSION_STEP_M if killing else EXPLOSION_FULL_M
    step_m = KILLING_EXPLOSION_STEP_M if killing else EXPLOSION_STEP_M
    if distance_m <= full_m:
        return 0
    return math.ceil(distance_m / step_m) - 1


def _explosion_dice(dice, power, lost: int):
    """6E1 p.325: "You always subtract the largest die rolled first".

    The half die, when there is one, is the last value in ``dice.damage``
    (`resolution/damage.py`) and the smallest Damage Class, so it goes only
    once every whole die has.
    """
    if lost <= 0:
        return dice, power
    full_n = int(power.damage_dice)
    full = list(dice.damage[:full_n])
    half = list(dice.damage[full_n:full_n + 1]) if power.half_die else []
    drop_full = min(lost, len(full))
    kept = sorted(full)[: len(full) - drop_full]
    half_die = bool(half) and lost <= len(full)
    return (replace(dice, damage=kept + (half if half_die else [])),
            replace(power, damage_dice=len(kept), half_die=half_die))


def _victims(session, spec, geo, attacker_id, no_range, enemies) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for cid in session.combatants:
        here = _position(session, cid)
        if here is None:
            continue
        if cid == attacker_id:
            # 6E1 p.321: centred on himself, "he takes full effect unless
            # he's somehow protected (such as ... Personal Immunity)"; a No
            # Range Cone or Line starts in front of him "but he takes no
            # damage from the attack" (p.322).
            if spec.personal_immunity:
                continue
            if no_range and spec.shape is not AreaShape.RADIUS:
                continue
        inside, d = _in_area(spec, geo, _xyz(here))
        if inside:
            out.append((cid, d))
    if spec.targeting is AreaTargeting.SELECTIVE:
        out = [(c, d) for c, d in out if c in enemies]
    return out


def _constructs_hit(session, spec, geo) -> list[Any]:
    from kirby_combat.actions.area_of_effect import _construct_point
    from kirby_combat.constructs import constructs_in

    scene = getattr(session, "scene", None)
    if scene is None:
        return []
    hit = []
    for c in constructs_in(scene, session=session) or []:
        if not getattr(c, "destructible", False):
            continue
        pt = _construct_point(c)
        if pt is None:
            continue
        # A construct is placed in plan (a segment or a footprint), so it
        # is tested in plan, at the area's own height.
        inside, _ = _in_area(spec, geo, (pt[0], pt[1], geo.point[2]))
        if inside:
            hit.append(c)
    return hit


def _record(session, event):
    from kirby_combat.session.apply import apply_event

    return apply_event(session, event)


@dataclass(frozen=True)
class AreaUse:
    """One use of an Area: where it landed, whom it holds, the use's row.

    ``failed`` is the result of a power that did not go off (6E1 p.375):
    then nothing else is set and the use covers nobody.
    """

    session: Any
    failed: Any
    use: Any
    to_hit: Any
    geo: "AreaGeometry | None"
    victims: list
    constructs: list
    decl_id: str | None
    landed: bool
    combat_type: str | None


@dataclass(frozen=True)
class _Aim:
    """Where an Area use goes and what its Attack Roll is made against."""

    shooter_xyz: Any
    geo: "AreaGeometry | None"
    roll_input: Any
    combat_type: str


def _aim(session, attack, combat_type) -> _Aim:
    """The target point and the roll against it, for `area_use` and for an
    Autofire burst that must know its margin before it lands
    (`area_attack_roll`)."""
    from kirby_combat.cv_modifiers import effective_ocv_for
    from kirby_combat.sense_penalties import HTH, RANGED

    attacker = session.combatants[attack.attacker.id]
    named = attack.target
    no_range = _no_range(attack.power)
    # WHERE THE AREA GOES. No Range: on the attacker (6E1 p.321-322).
    # Otherwise on the named target's own spot --- the offer named a man,
    # and Pulsar's example targets "the spot where Defender ... is standing".
    shooter = _position(session, attacker.id)
    aimed = _position(session, named.id)
    on_map = shooter is not None and aimed is not None
    if on_map:
        shooter_xyz, aimed_xyz = _xyz(shooter), _xyz(aimed)
        point = shooter_xyz if no_range else aimed_xyz
        geo = AreaGeometry(point=point, axis=_axis(shooter_xyz, aimed_xyz))
        range_m = 0.0 if no_range else math.dist(shooter_xyz, aimed_xyz)
    else:
        shooter_xyz = None
        geo = None
        range_m = None

    # THE ATTACK ROLL, against the point. 6E1 p.322: a No Range Area is
    # rolled "against DCV 0"; 6E2 p.42: a point within 2m is DCV 0.
    point_dcv = (ADJACENT_TARGET_POINT_DCV
                 if no_range or (range_m is not None and range_m <= ADJACENT_M)
                 else TARGET_POINT_DCV)
    combat_type = combat_type or (HTH if no_range else RANGED)
    ocv_delta = effective_ocv_for(
        session, attacker.id, against=named.id, combat_type=combat_type,
    ) - int(attacker.combat_stats().ocv)
    roll_input = replace(
        attack, target=_TargetPoint(dcv=point_dcv),
        distance_m=range_m if not no_range else None,
        ocv_modifier=attack.ocv_modifier + ocv_delta, dcv_modifier=0,
        fixed_to_hit=None,
    )
    return _Aim(shooter_xyz=shooter_xyz, geo=geo, roll_input=roll_input,
                combat_type=combat_type)


def area_attack_roll(session, attack, template, *, combat_type=None):
    """The Attack Roll an Area use makes against its target point, made
    without making the use. An Autofire Area burst rolls once and lands as
    many times as the roll's margin allows (6E2 p.45)."""
    from kirby_combat.resolution.to_hit import resolve_to_hit

    return resolve_to_hit(_aim(session, attack, combat_type).roll_input, template)


def area_use(session, attack, template, *, roller, declaration_event_id,
             action_type, combat_type) -> AreaUse:
    """Make the use: the Activation Roll, the Attack Roll against the target
    point, the scatter, who and what is in it, the use's own row, its END
    and its Side Effects. What it does to each man in it is the caller's:
    damage at the attack door (`resolve_area_attack_in_session`), a Flash or
    an Entangle (`actions/area_effects.py`)."""
    from kirby_combat.actions.recording import (
        _activation_check, _record_failed_activation, _spend_attack_end,
        apply_side_effects,
    )
    from kirby_combat.endurance import end_cost
    from kirby_combat.resolution.to_hit import resolve_to_hit
    from kirby_combat.roster import Roster
    from kirby_combat.session.events import (
        ActionDeclared, ActionResolved, make_author_combatant,
    )

    spec: AreaSpec = attack.power.area
    attacker = session.combatants[attack.attacker.id]
    named = attack.target
    roller = roller or session.dice_roller
    no_range = _no_range(attack.power)

    # AN AUTOFIRE BURST'S LANDING (6E2 p.45) arrives with the burst's one
    # Attack Roll already made, and its Activation Roll with it
    # (`actions/autofire_attack.py`): this use rolls neither.
    burst_roll = attack.fixed_to_hit
    # 6E1 p.375 first: a power that does not go off covers nobody.
    activated = None if burst_roll is not None else _activation_check(session, attack, roller)
    if activated is not None and not activated["activated"]:
        s, result = _record_failed_activation(
            session, attack, activated,
            declaration_event_id=declaration_event_id, action_type=action_type,
        )
        s = apply_side_effects(s, attack, template, roller=roller, failed=True)
        return AreaUse(session=s, failed=result, use=None, to_hit=None,
                       geo=None, victims=[], constructs=[], decl_id=None,
                       landed=False, combat_type=combat_type)

    aim = _aim(session, attack, combat_type)
    shooter_xyz, geo, combat_type = aim.shooter_xyz, aim.geo, aim.combat_type
    to_hit = (burst_roll if burst_roll is not None
              else resolve_to_hit(aim.roll_input, template))

    now = datetime.now(timezone.utc)
    s = session
    decl_id = declaration_event_id
    if decl_id is None:
        declared = ActionDeclared(
            id=str(uuid.uuid4()), session_id=s.id,
            sequence=len(s.event_log) + 1, timestamp=now,
            author=make_author_combatant(attacker.id),
            combatant_id=attacker.id, action_type=action_type,
            targets=[named.id],
            parameters={"power_xmlid": attack.power.xmlid, "area": True},
        )
        s = _record(s, declared)
        decl_id = declared.id

    deviated_m = 0.0
    if not to_hit.hit and geo is not None and not no_range:
        missed_by = abs(int(to_hit.margin))
        direction = int(sum(roller.roll_dice(1)))
        moved, deviated_m = _deviate(geo.point, shooter_xyz, missed_by, direction)
        geo = AreaGeometry(point=moved, axis=geo.axis)

    # WHO IS IN IT. A No Range miss affects nobody (6E1 p.322: "the attack
    # has no effect on anyone whatsoever").
    landed = to_hit.hit or (not no_range and geo is not None)
    enemies = {e.id for e in Roster(s).enemies_of(attacker)}
    if not landed:
        victims: list[tuple[str, float]] = []
        constructs: list[Any] = []
    elif geo is None:
        victims = [(named.id, 0.0)]           # RULING: no map, no neighbours
        constructs = []
    else:
        victims = _victims(s, spec, geo, attacker.id, no_range, enemies)
        constructs = ([] if spec.targeting in (AreaTargeting.SELECTIVE,
                                               AreaTargeting.NONSELECTIVE)
                      else _constructs_hit(s, spec, geo))
    if spec.targeting is AreaTargeting.ACCURATE:
        # 6E1 p.322: "automatically targeting only a single person".
        victims = [(c, d) for c, d in victims if c == named.id]

    # THE USE, ONCE: the row that carries the power's id (a Charge spent,
    # `charges.spent_charges`) and the END paid. The victims' rows carry
    # neither.
    use = ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id,
        sequence=len(s.event_log) + 1, timestamp=now,
        author=make_author_combatant(attacker.id),
        declaration_event_id=decl_id,
        result_payload={
            "kind": action_type,
            "area_use": True,
            "area_shape": spec.shape.value,
            "area_size_m": spec.size_m,
            "area_targeting": spec.targeting.value,
            "hit": to_hit.hit,
            "target_id": named.id,
            "stun_dealt": 0, "body_dealt": 0, "status_changes": [],
            "power_xmlid": attack.power.xmlid,
            "power_source_id": getattr(attack.power, "source_id", None),
            "power_name": getattr(attack.power, "name", None),
            "effective_ocv": to_hit.effective_ocv,
            "target_dcv": to_hit.effective_dcv,
            "margin": to_hit.margin,
            "target_point": list(geo.point) if geo is not None else None,
            "deviated_m": deviated_m,
            "victims": [c for c, _ in victims],
            "constructs": [getattr(c, "obj_id", None) for c in constructs],
            "segment": s.timeline.segment,
        },
    )
    s = _record(s, use)
    s = _spend_attack_end(s, attacker, end_cost(attack.power), template)
    s = apply_side_effects(s, attack, template, roller=roller, failed=False)
    return AreaUse(session=s, failed=None, use=use, to_hit=to_hit, geo=geo,
                   victims=victims, constructs=constructs, decl_id=decl_id,
                   landed=landed, combat_type=combat_type)


def resolve_area_attack_in_session(
    session: "CombatSession",
    attack: "AttackInput",
    template: "CombatTemplate",
    *,
    roller,
    declaration_event_id: str | None,
    action_type: str,
    combat_type: str | None,
    payload_extras: "Callable[[AttackResult], dict[str, Any]] | None",
) -> tuple["CombatSession", "AttackResult"]:
    """Resolve an Area Of Effect use: one roll, then every victim.

    Returns the session and the NAMED target's result (a miss result when
    the area did not catch him), so a caller that asked "did I hit the man I
    aimed at" is answered truthfully.
    """
    from kirby_combat.actions.recording import (
        resolve_attack_in_session,
    )
    from kirby_combat.endurance import end_cost
    from kirby_combat.models import AttackResult

    spec: AreaSpec = attack.power.area
    if spec.shape is AreaShape.SURFACE:
        # A Surface is not an area on the ground: it covers a thing, and
        # another man "has his standard DCV" (6E1 p.323). See
        # `standing_areas.resolve_surface_use`.
        from kirby_combat.standing_areas import resolve_surface_use

        return resolve_surface_use(
            session, attack, template, roller=roller,
            declaration_event_id=declaration_event_id,
            action_type=action_type, combat_type=combat_type,
            payload_extras=payload_extras,
        )
    placed = area_use(session, attack, template, roller=roller,
                      declaration_event_id=declaration_event_id,
                      action_type=action_type, combat_type=combat_type)
    if placed.failed is not None:
        return placed.session, placed.failed
    s, use, to_hit, geo = placed.session, placed.use, placed.to_hit, placed.geo
    victims, constructs, decl_id = placed.victims, placed.constructs, placed.decl_id
    landed, combat_type = placed.landed, placed.combat_type
    attacker = s.combatants[attack.attacker.id]
    named = attack.target
    roller = roller or session.dice_roller

    # EVERY VICTIM, through the door, with the one roll and the one damage
    # roll. The power goes in without its Area so the door does not come
    # back here.
    bare = replace(attack.power, area=None)
    named_result: AttackResult | None = None

    def _extras(result):
        extra = {"area_use_id": use.id}
        if payload_extras is not None:
            extra.update(payload_extras(result))
        return extra

    # A DAMAGE OVER TIME AREA DOES NOTHING ON THE USE: "the first increment
    # of damage affects the target one time period after the character uses
    # the attack" (6E1 p.331), and the zone keeps that clock (p.332). A
    # Constant one hits now, "the target takes the damage ... normally"
    # (6E1 p.129), and then stays.
    dot_zone = getattr(attack.power, "damage_over_time", None) is not None
    caught: list[str] = []
    for victim_id, distance in ([] if dot_zone else victims):
        victim = s.combatants[victim_id]
        dice, power = attack.dice, bare
        if spec.explosion:
            dice, power = _explosion_dice(dice, bare, explosion_dice_lost(
                distance, killing=bare.damage_type == "killing"))
        per_target = spec.targeting in (AreaTargeting.SELECTIVE,
                                        AreaTargeting.NONSELECTIVE)
        if per_target:
            # 6E1 p.326: "a separate Attack Roll against every target ...
            # at that target's normal DCV; the character suffers any
            # relevant modifiers to his OCV, such as the Range Modifier."
            dice = replace(dice, to_hit=roller.roll_dice(3))
            here = _position(s, attacker.id)
            there = _position(s, victim_id)
            dist = (math.dist(_xyz(here), _xyz(there))
                    if here is not None and there is not None else None)
        else:
            dist = None
        victim_attack = replace(
            attack, target=victim, power=power, dice=dice,
            distance_m=dist if per_target else None,
            fixed_to_hit=None if per_target else to_hit,
        )
        s, result = resolve_attack_in_session(
            s, victim_attack, template, declaration_event_id=decl_id,
            action_type=action_type, roller=roller, combat_type=combat_type,
            payload_extras=_extras, paid_use_event_id=use.id,
        )
        if victim_id == named.id:
            named_result = result
        if result.hit:
            caught.append(victim_id)

    for construct in ([] if dot_zone else constructs):
        s = _damage_construct(s, attacker, bare, attack.dice, construct,
                              template, roller, decl_id, use.id)

    # AND THEN IT STAYS. A Constant or Damage Over Time Area is a zone from
    # here on (`kirby_combat/standing_areas.py`): where it landed --- even
    # where a miss scattered it --- or, with No Range, on him. A No Range
    # miss "has no effect on anyone whatsoever" (6E1 p.322), so no zone.
    from kirby_combat.standing_areas import establish, is_standing

    if landed and is_standing(attack.power):
        s = establish(
            s, owner_id=attacker.id, power=attack.power,
            point=geo.point if geo is not None else None,
            axis=geo.axis if geo is not None else (1.0, 0.0),
            covered_id=None,
            # Selective: whoever the per-target rolls caught (6E1 p.326).
            # Damage Over Time: whoever was in it, whose clocks start now.
            affected=([c for c, _ in victims] if dot_zone else caught),
            use_event_id=use.id,
        )

    if named_result is None:
        named_result = AttackResult(
            hit=False, to_hit=to_hit, damage=None, defense=None,
            stun_dealt=0, body_dealt=0, end_spent=end_cost(attack.power),
            knockback=None, status_changes=[], power_xmlid=attack.power.xmlid,
            audit_trail=list(to_hit.audit) + [
                f"Area Of Effect ({spec.shape.value} {spec.size_m:g}m) "
                f"did not catch {named.id}"],
        )
    return s, named_result


def _damage_construct(s, attacker, power, dice, construct, template, roller,
                      decl_id, use_id):
    """A construct in the area takes the same damage roll (6E1 p.321)."""
    from kirby_combat.resolution.object_damage import apply_attack_to_construct
    from kirby_combat.session.events import ActionResolved, make_author_combatant

    outcome = apply_attack_to_construct(power, dice, construct, template)
    caught: list = []
    if outcome.destroyed:
        from kirby_combat.collapse import bring_it_down

        s, caught = bring_it_down(s, construct, roller=roller, template=template)
    return _record(s, ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id,
        sequence=len(s.event_log) + 1, timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(attacker.id),
        declaration_event_id=decl_id,
        # "attack_construct" so `constructs.damage_by_object` --- the one
        # ledger of what a building has lost --- counts it.
        result_payload={
            "kind": "attack_construct", "target_id": construct.obj_id,
            "body_dealt": outcome.body_through,
            "destroyed": outcome.destroyed, "collapsed_onto": caught,
            "area_use_id": use_id,
        },
    ))
