"""Areas that stay: Constant and Damage Over Time Areas, and Damage Shields.

An Area Of Effect attack lands once (`actions/area_attack.py`). Buy it
Constant or Damage Over Time and it stops being an attack on a place and
becomes a place --- a zone in the scene that goes on hurting whoever is in
it and whoever walks into it. Batch C built the one-shot area and stopped
offering these, because nothing in the engine could keep a zone. This
module is the zone.

THE RULES, page by page:

  * Constant, 6E1 p.129: "If a Constant Power affects an Area ... the Power
    remains in effect in the Segments between the attacker's Phases. Any
    target who enters the area takes damage or is affected in the Segment
    he enters and every time the attacker's Phase occurs while the target
    remains within the area. If a character enters a Constant
    Area-affecting power's field of effect more than once per Phase, he
    does not suffer the damage (or other effect) multiple times."
    Maintenance is the Constant rule (p.129-130): END paid "when the
    character's Phase begins, before he does anything else", Line Of Sight
    "to the location of the Power", and p.347's "turns off at the end of
    the Segment whenever the character is asleep, Stunned, or Knocked Out".
  * Damage Over Time, 6E1 p.332: "If an Damage Over Time power is an Area
    Of Effect, the effect remains in all Segments for its defined
    duration, not just the attacker's Phases. Any character who enters the
    area takes damage or suffer the power's effects (no Attack Roll is
    required) that Segment and after each damage interval thereafter until
    he leaves the area."
  * Selective and Nonselective, 6E1 p.326: a Selective Constant area
    "cannot alter whom the power affects every Phase", and a man who enters
    it later needs an Attack Roll "this takes no time"; a Nonselective one
    makes "an Attack Roll against each person in the affected area every
    Phase ... part of 'maintaining' the Constant Area Of Effect".
  * Moving with him, 6E1 p.326: a Constant Area-affecting power "cannot
    move once established, unless it has the No Range Limitation so that
    it 'sticks to' the character generating it and moves as he moves (see
    6E1 127)" --- and p.129 offers the same at the GM's option. "As it
    sweeps over an area, the standard rules for Constant Area-affecting
    powers apply."
  * Damage Shield, 6E1 p.323-324: "A Constant Area Of Effect (personal
    Surface; +1/4) power that a character applies to himself". It hurts
    whoever he hits or Grabs and whoever hits or Grabs him, with no Attack
    Roll, against the victim's defenses; it is switched on with a Zero
    Phase Action and "costs END every Phase it remains active".
  * Persistent, 6E1 p.130: "assumed to be on at all times, even when the
    character is unconscious". A Persistent No Range aura or Damage Shield
    is never switched on: it is part of him from the first Segment.

THE RECORD (`session/effects.py`'s house pattern): a
`StandingAreaEstablished` when the zone is made, every dose an
`ActionResolved` through the attack door carrying ``standing_area_id``,
and a `StandingAreaEnded`. Where a zone that moves with its owner lies is
never written down: it is wherever the log has put him. A Persistent zone
has no `StandingAreaEstablished` at all --- it is read off the build, with
an id built from the man and the power, so a replay finds it the same way.

RULINGS (each labelled where it is made):

  * "Once per Phase" for entering is counted between the OWNER's Phases:
    the zone's own clock, the one its Phase doses keep.
  * A man who is in a zone when it is set up is not "entering" it; the
    attack that set it up was his dose (Constant), or his clock starts with
    it (Damage Over Time).
  * Entering is read from the straight line between where a move started
    and where it ended, the only path the log keeps (`MovementResolved`).
  * Everyone in a zone takes its dose, down or not; the dead do not.
  * The attacker never chooses to switch a zone off, as Batch C ruled for
    the one-target Constant attack (`lingering.py`).
  * The wearer of a Damage Shield is not hurt by it (6E1 p.323-324 give its
    damage only to the people he touches); the shield never hits itself.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from kirby_combat.encounter import SEGMENTS_PER_TURN
from kirby_combat.lingering import absolute_segment
from kirby_combat.power_modifiers import AreaShape, AreaTargeting

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


class StandingMode(str, Enum):
    CONSTANT = "constant"
    DAMAGE_OVER_TIME = "damage_over_time"


class StandingEnd(str, Enum):
    """Why a zone stopped (`StandingAreaEnded.reason`)."""

    RAN_ITS_COURSE = "ran_its_course"                 # 6E1 p.332
    NO_END = "could_not_pay_end"                      # 6E1 p.129
    LOST_LINE_OF_SIGHT = "lost_line_of_sight"         # 6E1 p.129
    OWNER_STUNNED = "owner_stunned_or_out"            # 6E1 p.347
    SLOT_SWITCHED = "slot_switched_off"               # 6E1 p.400
    RECOVERED = "owner_took_a_recovery"               # 6E2 p.131
    POWER_NOT_ON_BUILD = "power_not_on_build"


class Dose(str, Enum):
    """What a zone's dose was for (``standing_dose`` on the row)."""

    PHASE = "phase"          # the owner's Phase came round (6E1 p.129)
    ENTERED = "entered"      # he walked in (6E1 p.129, p.332)
    INTERVAL = "interval"    # a Damage Over Time increment fell due (p.332)
    CONTACT = "contact"      # he touched a Damage Shield, or it him (p.323)


#: The offer that switches a Damage Shield on: "he only has to use a Zero
#: Phase Action to activate it" (6E1 p.323). A Zero Phase Action, so the
#: Phase comes back to him (`loop/run.py`).
RAISE_DAMAGE_SHIELD = "raise_damage_shield"

#: Sampling step along a move, metres. Fine enough that no 1m Radius is
#: stepped over; the path itself is the log's straight line (RULING above).
_PATH_STEP_M = 0.5


@dataclass(frozen=True)
class StandingArea:
    """One zone, as the log has it now."""

    id: str
    owner_id: str
    power_source_id: str
    mode: StandingMode
    shape: AreaShape
    #: Where it was set down. A zone that follows its owner is wherever he
    #: is (`point_now`); this is where it started.
    point: tuple[float, float, float] | None
    axis: tuple[float, float]
    follows_owner: bool
    #: For a Surface: whose skin is covered. Otherwise None.
    covered_id: str | None
    #: Selective: the people it works on (6E1 p.326). Everyone else in it
    #: is spared.
    affected: frozenset[str]
    increments: int | None
    interval_segments: int | None
    established_at: int
    established_seq: int
    persistent: bool
    ended: bool


# ---------------------------------------------------------------------------
# Reading it off the log (and, for a Persistent zone, off the build)
# ---------------------------------------------------------------------------

def _views(combatant) -> list:
    attacks = getattr(combatant, "attacks", None)
    attacks = attacks() if callable(attacks) else attacks
    return list(attacks or [])


def is_personal_surface(power) -> bool:
    """A Damage Shield: a Surface on his own skin (6E1 p.323). A Surface
    power with No Range, by Limitation or by nature, is applied to
    himself: "If a Damage Shield involves a Ranged power, it must take the
    No Range (-1/2) Limitation"."""
    area = getattr(power, "area", None)
    return (area is not None and area.shape is AreaShape.SURFACE
            and not getattr(power, "is_ranged", False))


def is_standing(power) -> bool:
    """Does a use of this power leave a zone behind?"""
    area = getattr(power, "area", None)
    return area is not None and (
        bool(getattr(power, "constant", False))
        or getattr(power, "damage_over_time", None) is not None)


def is_always_on(power) -> bool:
    """Persistent and No Range: on from the first Segment, never switched
    on, never offered (6E1 p.130). A Persistent power bought at range still
    has to be put somewhere, which is an Attack."""
    return (is_standing(power) and bool(getattr(power, "persistent", False))
            and not getattr(power, "is_ranged", False))


def _persistent_id(owner_id: str, source_id: str) -> str:
    return f"persistent:{owner_id}:{source_id}"


def _slot_on(session, owner_id: str, power) -> bool:
    framework_id = str(getattr(power, "framework_id", "") or "")
    slot_id = str(getattr(power, "slot_id", "") or "")
    if not framework_id or not slot_id:
        return True
    from kirby_combat.framework import active_slots

    active = active_slots(session, owner_id, framework_id)
    return not active or slot_id in active


def _implicit(session) -> list[StandingArea]:
    out = []
    for cid, combatant in session.combatants.items():
        for power in _views(combatant):
            if not is_always_on(power) or not _slot_on(session, cid, power):
                continue
            source = str(getattr(power, "source_id", "") or "")
            if not source:
                raise ValueError(
                    f"Persistent area power {getattr(power, 'name', '?')!r} on "
                    f"{cid} has no source_id; a dose has to find it again")
            out.append(StandingArea(
                id=_persistent_id(cid, source), owner_id=cid,
                power_source_id=source, mode=StandingMode.CONSTANT,
                shape=power.area.shape, point=None, axis=(1.0, 0.0),
                follows_owner=True,
                covered_id=cid if power.area.shape is AreaShape.SURFACE else None,
                affected=frozenset(), increments=None, interval_segments=None,
                established_at=0, established_seq=0, persistent=True,
                ended=False,
            ))
    return out


def standing_areas(session: "CombatSession") -> list[StandingArea]:
    """Every zone in this fight, folded forward from the log, then the
    Persistent ones read off the builds."""
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for event in session.event_log:
        kind = getattr(event, "kind", "")
        if kind == "StandingAreaEstablished":
            point = event.point or None
            by_id[event.id] = {
                "id": event.id, "owner_id": event.owner_id,
                "power_source_id": event.power_source_id,
                "mode": StandingMode(event.mode),
                "shape": AreaShape(event.shape),
                "point": ((float(point["x"]), float(point["y"]),
                           float(point.get("z", 0.0)))
                          if point else None),
                "axis": (float(event.axis.get("x", 1.0)),
                         float(event.axis.get("y", 0.0))),
                "follows_owner": bool(event.follows_owner),
                "covered_id": event.covered_id or None,
                "affected": frozenset(event.affected or ()),
                "increments": event.increments,
                "interval_segments": event.interval_segments,
                "established_at": absolute_segment(event.established_turn,
                                                   event.established_segment),
                "established_seq": event.sequence,
                "persistent": bool(event.persistent),
                "ended": False,
            }
            order.append(event.id)
        elif kind == "ActionResolved":
            payload = getattr(event, "result_payload", None) or {}
            sid = payload.get("standing_area_id")
            if sid in by_id and payload.get("hit") and payload.get(
                    "standing_dose") == Dose.ENTERED.value:
                # A Selective zone works on whoever it was rolled onto as he
                # came in (6E1 p.326).
                by_id[sid]["affected"] = by_id[sid]["affected"] | {
                    payload.get("target_id")}
        elif kind == "StandingAreaEnded":
            if event.area_id in by_id:
                by_id[event.area_id]["ended"] = True
    out = [StandingArea(**by_id[i]) for i in order]
    ended_implicit = {e.area_id for e in session.event_log
                      if getattr(e, "kind", "") == "StandingAreaEnded"}
    out.extend(a for a in _implicit(session) if a.id not in ended_implicit)
    return out


def active_standing_areas(session, *, owner_id: str | None = None,
                          mode: StandingMode | None = None) -> list[StandingArea]:
    return [a for a in standing_areas(session)
            if not a.ended
            and (owner_id is None or a.owner_id == owner_id)
            and (mode is None or a.mode is mode)]


def damage_shields_on(session, combatant_id: str) -> list[StandingArea]:
    """The Damage Shields this man is wearing now."""
    return [a for a in active_standing_areas(session, owner_id=combatant_id)
            if a.shape is AreaShape.SURFACE and a.covered_id == combatant_id]


def power_of(session, area: StandingArea):
    owner = session.combatants.get(area.owner_id)
    if owner is None:
        return None
    for ap in _views(owner):
        if str(getattr(ap, "source_id", "") or "") == area.power_source_id:
            return ap
    return None


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def _positions(session) -> dict:
    scene = getattr(session, "scene", None)
    if scene is None:
        return {}
    return getattr(scene, "combatant_positions", None) or {}


def _xyz(p) -> tuple[float, float, float]:
    if isinstance(p, dict):
        return (float(p["x"]), float(p["y"]), float(p.get("z", 0.0) or 0.0))
    return (float(p.x), float(p.y), float(getattr(p, "z", 0.0) or 0.0))


def point_now(session, area: StandingArea, *, owner_at=None):
    """Where the zone is now: where it was set down, or on its owner."""
    if not area.follows_owner:
        return area.point
    here = owner_at if owner_at is not None else _positions(session).get(area.owner_id)
    return None if here is None else _xyz(here)


def _contains(spec, point, axis, here) -> tuple[bool, float]:
    from kirby_combat.actions.area_attack import AreaGeometry, _in_area

    return _in_area(spec, AreaGeometry(point=point, axis=axis), here)


def _spared(area: StandingArea, power, cid: str) -> bool:
    """The owner in his own zone (6E1 p.321-322), as `area_attack._victims`
    rules for the use that made it."""
    if cid != area.owner_id:
        return False
    spec = power.area
    if spec.personal_immunity:
        return True
    return (not getattr(power, "is_ranged", False)
            and spec.shape is not AreaShape.RADIUS)


def occupants(session, area: StandingArea, power) -> list[tuple[str, float]]:
    """Who is in the zone now, and how far from its point (Explosion)."""
    point = point_now(session, area)
    positions = _positions(session)
    if point is None or not positions:
        # RULING (Batch C's for any area): no map, no neighbours --- the
        # zone holds whoever it was first laid on.
        return [(c, 0.0) for c in sorted(area.affected)
                if c in session.combatants]
    out = []
    for cid in session.combatants:
        here = positions.get(cid)
        if here is None or _spared(area, power, cid):
            continue
        inside, d = _contains(power.area, point, area.axis, _xyz(here))
        if inside:
            out.append((cid, d))
    return out


def _path(frm, to):
    d = math.dist(frm, to)
    steps = max(1, int(math.ceil(d / _PATH_STEP_M)))
    return [tuple(frm[i] + (to[i] - frm[i]) * k / steps for i in range(3))
            for k in range(steps + 1)]


# ---------------------------------------------------------------------------
# Writing it down
# ---------------------------------------------------------------------------

def _apply(session, event):
    from kirby_combat.session.apply import apply_event

    return apply_event(session, event)


def end_area(session, area_id: str, reason: StandingEnd):
    from kirby_combat.session.events import StandingAreaEnded, make_author_engine

    return _apply(session, StandingAreaEnded(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        area_id=area_id, reason=reason.value,
    ))


def establish(session, *, owner_id: str, power, point, axis,
              covered_id: str | None, affected, use_event_id: str):
    """Write down a zone the use ``use_event_id`` has just made."""
    from kirby_combat.session.events import (
        StandingAreaEstablished, make_author_combatant,
    )

    source = str(getattr(power, "source_id", "") or "")
    if not source:
        raise ValueError(
            f"standing area power {getattr(power, 'name', '?')!r} has no "
            "source_id; a later dose has to find the power again by its id")
    dot = getattr(power, "damage_over_time", None)
    mode = (StandingMode.DAMAGE_OVER_TIME if dot is not None
            else StandingMode.CONSTANT)
    follows = not getattr(power, "is_ranged", False)
    return _apply(session, StandingAreaEstablished(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(owner_id),
        owner_id=owner_id, power_source_id=source,
        power_name=str(getattr(power, "name", "")), mode=mode.value,
        shape=power.area.shape.value, size_m=float(power.area.size_m),
        point=({"x": point[0], "y": point[1], "z": point[2]}
               if point is not None else {}),
        axis={"x": axis[0], "y": axis[1]},
        follows_owner=follows, covered_id=covered_id or "",
        affected=sorted(affected), persistent=bool(getattr(power, "persistent", False)),
        increments=dot.increments if dot is not None else None,
        interval_segments=dot.interval_segments if dot is not None else None,
        established_turn=session.timeline.turn,
        established_segment=session.timeline.segment,
        use_event_id=use_event_id,
    ))


# ---------------------------------------------------------------------------
# Doses
# ---------------------------------------------------------------------------

def _bare(power):
    return replace(power, constant=False, damage_over_time=None, area=None,
                   side_effects=None)


def _roll(power, roller):
    from kirby_combat.models import DiceValues

    bare = _bare(power)
    count = max(1, int(bare.damage_dice or 0)) + (1 if bare.half_die else 0)
    return DiceValues(to_hit=[], damage=roller.roll_dice(count),
                      hit_location=roller.roll_dice(3),
                      stun_multiplier=roller.roll_dice(1))


def _no_roll(page: str):
    from kirby_combat.models import ToHitResult

    return ToHitResult(
        hit=True, roll=0, target_number=0, margin=0, effective_ocv=0,
        effective_dcv=0, range_penalty=0, hit_location_penalty=0,
        csl_bonus=0, audit=[f"standing area: no Attack Roll ({page})"],
    )


def _dead(session, cid: str) -> bool:
    from kirby_combat.statuses import DEAD, statuses_for

    return DEAD in statuses_for(session, cid)


def dose(session, area: StandingArea, power, victim_id: str, *, dice,
         distance_m: float, why: Dose, template, roller,
         movement_event_id: str | None = None, roll_to_hit: bool = False):
    """One dose of the zone on one man, through the attack door.

    No Attack Roll unless the book asks for one (a Selective zone's
    newcomer, a Nonselective zone's every Phase: 6E1 p.326), and never END:
    the use paid, or the maintenance did.
    """
    from kirby_combat.actions.area_attack import _explosion_dice, explosion_dice_lost
    from kirby_combat.actions.recording import resolve_attack_in_session
    from kirby_combat.models import AttackInput
    from kirby_combat.sense_penalties import RANGED

    owner = session.combatants[area.owner_id]
    victim = session.combatants[victim_id]
    bare = _bare(power)
    if power.area.explosion:
        dice, bare = _explosion_dice(dice, bare, explosion_dice_lost(
            distance_m, killing=bare.damage_type == "killing"))
    page = {Dose.PHASE: "6E1 p.129", Dose.ENTERED: "6E1 p.129, p.332",
            Dose.INTERVAL: "6E1 p.332", Dose.CONTACT: "6E1 p.323"}[why]
    distance = None
    if roll_to_hit:
        dice = replace(dice, to_hit=roller.roll_dice(3))
        positions = _positions(session)
        a, v = positions.get(area.owner_id), positions.get(victim_id)
        if a is not None and v is not None and getattr(power, "is_ranged", False):
            # 6E1 p.326: "the Range Modifier applies to all targets".
            distance = math.dist(_xyz(a), _xyz(v))
    attack = AttackInput(
        attacker=owner, target=victim, power=bare, distance_m=distance,
        aim=None, dice=dice,
        fixed_to_hit=None if roll_to_hit else _no_roll(page),
    )
    extras = {
        "standing_area_id": area.id, "standing_dose": why.value,
        "turn": session.timeline.turn,
    }
    if movement_event_id is not None:
        extras["movement_event_id"] = movement_event_id
    # Never a HTH blow, so never Blocked: "Characters cannot avoid Area Of
    # Effect attacks by Dodging or Deflecting them" (6E1 p.321), and a
    # Block (6E2 p.59) answers a blow, not a place or a burning skin.
    session, _ = resolve_attack_in_session(
        session, attack, template, declaration_event_id=area.id,
        action_type="attack", roller=roller, paid_use_event_id=area.id,
        combat_type=RANGED,
        payload_extras=lambda _r: dict(extras),
    )
    return session


def _dose_rows(session, area_id: str) -> list:
    return [e for e in session.event_log
            if e.kind == "ActionResolved"
            and (e.result_payload or {}).get("standing_area_id") == area_id]


def _when(event) -> int:
    payload = event.result_payload or {}
    return absolute_segment(int(payload.get("turn", 1) or 1),
                            int(payload.get("segment", 1) or 1))


# ---------------------------------------------------------------------------
# The owner's Phase: pay, then hurt everyone in it --- or let it go
# ---------------------------------------------------------------------------

def _owner_out_since(session, owner_id: str, since_seq: int) -> bool:
    """6E1 p.347: a Constant power "turns off at the end of the Segment
    whenever the character is asleep, Stunned, or Knocked Out"."""
    from kirby_combat.enumeration import is_down
    from kirby_combat.statuses import stunned_or_recovering_for

    owner = session.combatants.get(owner_id)
    if owner is None or is_down(owner):
        return True
    if stunned_or_recovering_for(session, owner_id):
        return True
    for event in session.event_log:
        if event.sequence <= since_seq or event.kind != "ActionResolved":
            continue
        payload = event.result_payload or {}
        if payload.get("target_id") == owner_id and (
                {"Stunned", "Knocked Out"} & set(payload.get("status_changes") or ())):
            return True
    return False


def _sees_the_point(session, area: StandingArea) -> bool:
    """6E1 p.129: "the character must maintain a Line Of Sight to the
    location of the Power"."""
    if area.follows_owner or area.point is None:
        return True
    scene = getattr(session, "scene", None)
    here = _positions(session).get(area.owner_id)
    if scene is None or here is None:
        return True
    from kirby_world.geometry import line_of_sight_clear
    from kirby_world.scene import Position

    p = area.point
    return line_of_sight_clear(here, Position(p[0], p[1], p[2]),
                               getattr(scene, "walls", None) or [])


def _keep_or_end(session, area: StandingArea, power):
    """The reason this zone stops now, or None. Damage Over Time is asked
    nothing about its owner: "If the caster is Stunned or Knocked Out, or
    loses Line Of Sight on the target, the power continues to function as
    intended" (6E1 p.332)."""
    if power is None:
        return StandingEnd.POWER_NOT_ON_BUILD
    if not _slot_on(session, area.owner_id, power):
        return StandingEnd.SLOT_SWITCHED
    if area.mode is StandingMode.DAMAGE_OVER_TIME:
        return None
    if not area.persistent and _owner_out_since(
            session, area.owner_id, area.established_seq):
        return StandingEnd.OWNER_STUNNED
    if not _sees_the_point(session, area):
        return StandingEnd.LOST_LINE_OF_SIGHT
    return None


def maintain_standing_areas(session, actor_id: str, *, template, roller):
    """At the start of the owner's Phase (6E1 p.130: "paid when the
    character's Phase begins, before he does anything else"), every Constant
    zone and Damage Shield he keeps: pay its END, then dose everyone in it.

    Maintaining takes no Action (6E1 p.129), so the Phase is still his.
    """
    from kirby_combat.actions.recording import _spend_attack_end
    from kirby_combat.endurance import end_available, end_cost

    for area in active_standing_areas(session, owner_id=actor_id,
                                      mode=StandingMode.CONSTANT):
        power = power_of(session, area)
        reason = _keep_or_end(session, area, power)
        if reason is not None:
            if not area.persistent or reason is StandingEnd.POWER_NOT_ON_BUILD:
                session = end_area(session, area.id, reason)
            continue
        owner = session.combatants[actor_id]
        cost = end_cost(power)
        left = end_available(session, actor_id, power=power, template=template)
        if cost and left is not None and left < cost:
            # RULING (as `lingering.maintain_constant_attacks`): he stops
            # rather than burn STUN for END (6E2 p.133 permits it).
            session = end_area(session, area.id, StandingEnd.NO_END)
            continue
        session = _spend_attack_end(session, owner, cost, template, power=power)
        if area.shape is AreaShape.SURFACE:
            # A Damage Shield does its work on contact --- and a man he
            # holds is in contact with it: "A Grabbed character takes the
            # damage from the Shield every time the attacker has a Phase"
            # (6E1 p.324).
            session = _held_doses(session, area, power, template=template,
                                  roller=roller)
            continue
        session = _phase_doses(session, area, power, template=template,
                               roller=roller)
    return session


def _held_doses(session, area, power, *, template, roller):
    from kirby_combat.grappling import session_holds

    holds = session_holds(session)
    for cid in list(session.combatants):
        if cid != area.owner_id and holds.grabbed_by(cid) == area.owner_id \
                and not _dead(session, cid):
            session = dose(session, area, power, cid, dice=_roll(power, roller),
                           distance_m=0.0, why=Dose.CONTACT,
                           template=template, roller=roller)
    return session


def _phase_doses(session, area, power, *, template, roller):
    from kirby_combat.actions.area_attack import _constructs_hit, _damage_construct, AreaGeometry

    spec = power.area
    inside = [(c, d) for c, d in occupants(session, area, power)
              if not _dead(session, c)]
    if spec.targeting is AreaTargeting.SELECTIVE or spec.targeting is AreaTargeting.ACCURATE:
        # 6E1 p.326: "the attacker cannot alter whom the power affects
        # every Phase"; Accurate is "only a single person" (p.322).
        inside = [(c, d) for c, d in inside if c in area.affected]
    dice = _roll(power, roller)
    for cid, distance in inside:
        session = dose(session, area, power, cid, dice=dice,
                       distance_m=distance, why=Dose.PHASE,
                       template=template, roller=roller,
                       roll_to_hit=spec.targeting is AreaTargeting.NONSELECTIVE)
    point = point_now(session, area)
    if point is not None and spec.targeting is AreaTargeting.STANDARD:
        # "Area Of Effect attacks completely fill the affected area" (6E1
        # p.321): a wall in a burning zone burns every Phase too.
        geo = AreaGeometry(point=point, axis=area.axis)
        owner = session.combatants[area.owner_id]
        for construct in _constructs_hit(session, spec, geo):
            session = _damage_construct(session, owner, _bare(power), dice,
                                        construct, template, roller,
                                        area.id, area.id)
    return session


# ---------------------------------------------------------------------------
# The top of every Segment: Damage Over Time increments
# ---------------------------------------------------------------------------

def tick_standing_areas(session, *, template, roller):
    """Every Damage Over Time zone: whoever has been in it a whole interval
    since his last dose takes another (6E1 p.332), and a zone whose
    "defined duration" is over ends."""
    now = absolute_segment(session.timeline.turn, session.timeline.segment)
    for area in active_standing_areas(session, mode=StandingMode.DAMAGE_OVER_TIME):
        power = power_of(session, area)
        reason = _keep_or_end(session, area, power)
        if reason is not None:
            session = end_area(session, area.id, reason)
            continue
        interval = int(area.interval_segments or 0)
        lasts_until = area.established_at + interval * int(area.increments or 0)
        rows = _dose_rows(session, area.id)
        last: dict[str, int] = {}
        for row in rows:
            p = row.result_payload or {}
            if p.get("hit"):
                last[p.get("target_id")] = max(last.get(p.get("target_id"), -1),
                                               _when(row))
        due = []
        for cid, distance in occupants(session, area, power):
            if _dead(session, cid):
                continue
            since = last.get(cid)
            if since is None:
                if cid not in area.affected:
                    # In it with no clock: the zone came to him without a
                    # move the log shows. He has entered it, now.
                    due.append((cid, distance, Dose.ENTERED))
                    continue
                since = area.established_at
            if now >= since + interval and now <= lasts_until:
                due.append((cid, distance, Dose.INTERVAL))
        if due:
            dice = _roll(power, roller)
            for cid, distance, why in due:
                session = dose(session, area, power, cid, dice=dice,
                               distance_m=distance, why=why,
                               template=template, roller=roller)
        if now >= lasts_until:
            session = end_area(session, area.id, StandingEnd.RAN_ITS_COURSE)
    return session


# ---------------------------------------------------------------------------
# After a Phase: who walked in, and whether he Recovered
# ---------------------------------------------------------------------------

def _owner_phase_start(session, owner_id: str, t: int) -> int:
    """The latest Segment at or before ``t`` in which the owner had a Phase
    --- the start of the window "once per Phase" counts in (RULING above)."""
    from kirby_combat.tables import segments_for_spd

    owner = session.combatants.get(owner_id)
    spd = int(owner.combat_stats().spd) if owner is not None else 0
    phases = segments_for_spd(spd)
    if not phases:
        return -1
    for back in range(0, SEGMENTS_PER_TURN + 1):
        s = t - back
        if s < 0:
            break
        seg = (s - 1) % SEGMENTS_PER_TURN + 1
        if seg in phases:
            return s
    return -1


def _entered_this_window(session, area, mover: str, t: int) -> bool:
    start = _owner_phase_start(session, area.owner_id, t)
    for row in _dose_rows(session, area.id):
        p = row.result_payload or {}
        if (p.get("target_id") == mover
                and p.get("standing_dose") == Dose.ENTERED.value
                and _when(row) >= start):
            return True
    return False


def _moves_handled(session, area_id: str) -> set[str]:
    return {(row.result_payload or {}).get("movement_event_id")
            for row in _dose_rows(session, area_id)} - {None}


def _entrants(session, area, power, move) -> list[tuple[str, float]]:
    """Who this one move brings into the zone, and how far from its point
    (for an Explosion) he first was inside."""
    if move.from_pos is None or move.to_pos is None:
        return []
    frm, to = _xyz(move.from_pos), _xyz(move.to_pos)
    mover = move.combatant_id
    spec = power.area
    if area.follows_owner and mover == area.owner_id:
        # The zone moved with him and "sweeps over an area" (6E1 p.326):
        # whoever it now covers that it did not before has entered it.
        before, after = frm, to
        out = []
        for cid, here in _positions(session).items():
            if cid not in session.combatants or _spared(area, power, cid):
                continue
            h = _xyz(here)
            was, _ = _contains(spec, before, area.axis, h)
            if was:
                continue
            for p in _path(before, after):
                inside, d = _contains(spec, p, area.axis, h)
                if inside:
                    out.append((cid, d))
                    break
        return out
    point = point_now(session, area)
    if point is None or _spared(area, power, mover):
        return []
    was, _ = _contains(spec, point, area.axis, frm)
    if was:
        return []
    for p in _path(frm, to):
        inside, d = _contains(spec, point, area.axis, p)
        if inside:
            return [(mover, d)]
    return []


def entries_since(session, since: int, *, template, roller):
    """Everyone a move since log index ``since`` carried into a zone takes
    the zone's entering dose: "in the Segment he enters" (6E1 p.129) and
    "that Segment" (p.332)."""
    from kirby_combat.roster import Roster

    moves = [e for e in session.event_log[since:]
             if getattr(e, "kind", "") == "MovementResolved"]
    if not moves:
        return session
    for area in active_standing_areas(session):
        if area.shape is AreaShape.SURFACE:
            continue
        power = power_of(session, area)
        if power is None:
            continue
        handled = _moves_handled(session, area.id)
        spec = power.area
        for move in moves:
            if move.sequence <= area.established_seq or move.id in handled:
                continue
            now = absolute_segment(session.timeline.turn, session.timeline.segment)
            for cid, distance in _entrants(session, area, power, move):
                if cid not in session.combatants or _dead(session, cid):
                    continue
                if (area.mode is StandingMode.CONSTANT
                        and _entered_this_window(session, area, cid, now)):
                    # 6E1 p.129: "more than once per Phase, he does not
                    # suffer the damage ... multiple times".
                    continue
                roll = False
                if area.mode is StandingMode.CONSTANT:
                    if spec.targeting is AreaTargeting.ACCURATE:
                        continue            # it works on one man, already chosen
                    if spec.targeting is AreaTargeting.SELECTIVE:
                        owner = session.combatants[area.owner_id]
                        enemies = {e.id for e in Roster(session).enemies_of(owner)}
                        if cid not in enemies:
                            # RULING: he wants to affect his enemies only ---
                            # "he can ignore 'friendlies'" (p.326).
                            continue
                        roll = True     # "he must make an Attack Roll to do so"
                    elif spec.targeting is AreaTargeting.NONSELECTIVE:
                        roll = True
                session = dose(session, area, power, cid,
                               dice=_roll(power, roller), distance_m=distance,
                               why=Dose.ENTERED, template=template,
                               roller=roller, movement_event_id=move.id,
                               roll_to_hit=roll)
    return session


def after_the_phase(session, actor_id: str, *, since: int, recovered: bool,
                    template, roller):
    """What a Phase does to the zones: the moves it made bring people into
    them, and a man who Recovered keeps none of his Constant ones --- "He
    cannot even maintain a Constant Power (even if it only costs END to
    activate)" (6E2 p.131). A Damage Over Time zone "doesn't affect and
    isn't affected by taking a Recovery" (same page)."""
    if recovered:
        for area in active_standing_areas(session, owner_id=actor_id,
                                          mode=StandingMode.CONSTANT):
            if not area.persistent:
                session = end_area(session, area.id, StandingEnd.RECOVERED)
        from kirby_combat.lingering import (
            LingeringEnd, LingeringMode, _end as _end_lingering, active_lingering,
        )

        for effect in active_lingering(session, attacker_id=actor_id,
                                       mode=LingeringMode.CONSTANT):
            session = _end_lingering(session, effect.id, LingeringEnd.RECOVERED)
    session = _grabs_since(session, since, template=template, roller=roller)
    return entries_since(session, since, template=template, roller=roller)


def _grabs_since(session, since: int, *, template, roller):
    """A Grab is contact both ways (6E1 p.323: "Grabbing him", and the
    Grabber of a shielded man "takes the Shield's damage"). The Grab is
    resolved off the attack door (`actions/grab.py`), so it is read here
    from the rows the Phase wrote."""
    for event in list(session.event_log[since:]):
        if getattr(event, "kind", "") != "ActionResolved":
            continue
        p = event.result_payload or {}
        if p.get("type") == "grab" and p.get("hit"):
            session = contact_doses(session, p["attacker_id"], p["target_id"],
                                    template=template, roller=roller,
                                    contact_event_id=event.id)
    return session


# ---------------------------------------------------------------------------
# Contact: Damage Shields, and a Surface laid on another man
# ---------------------------------------------------------------------------

def covered_skins(session, combatant_id: str) -> list[tuple[StandingArea | None, Any, str]]:
    """Every covered Surface on this man's skin: ``(zone, power, owner)``.

    His own Damage Shields, and a Constant Surface somebody else has laid
    on him and is maintaining (`lingering.py` keeps that one: it is a
    Constant attack on him, and its Surface is what makes his skin catch
    whoever touches it, 6E1 p.323: "any character who comes into contact
    with that Surface suffers the Power's effects immediately").
    """
    from kirby_combat.lingering import LingeringMode, _power_of, active_lingering

    out: list = []
    for area in damage_shields_on(session, combatant_id):
        power = power_of(session, area)
        if power is not None:
            out.append((area, power, area.owner_id))
    for effect in active_lingering(session, target_id=combatant_id,
                                   mode=LingeringMode.CONSTANT):
        power = _power_of(session, effect)
        area = getattr(power, "area", None)
        if area is not None and area.shape is AreaShape.SURFACE:
            out.append((None, power, effect.attacker_id))
    return out


def contact_doses(session, attacker_id: str, target_id: str, *, template,
                  roller, contact_event_id: str):
    """A blow landed hand to hand: each covered skin the two men touched
    hurts the other one (6E1 p.323, both ways), once for this Attack Roll
    ("once for each Attack Roll", p.323)."""
    for wearer, other in ((target_id, attacker_id), (attacker_id, target_id)):
        if other not in session.combatants or wearer not in session.combatants:
            continue
        for area, power, owner in covered_skins(session, wearer):
            if other == owner:
                continue        # RULING: his own power on his own skin
            session = _contact_dose(session, area, power, owner, other,
                                    template=template, roller=roller,
                                    contact_event_id=contact_event_id)
    return session


def _contact_dose(session, area, power, owner_id, victim_id, *, template,
                  roller, contact_event_id):
    if area is None:
        # A Surface laid on another man: the dose is the layer's power,
        # declared by the attack that made the contact.
        area = StandingArea(
            id=contact_event_id, owner_id=owner_id,
            power_source_id=str(power.source_id), mode=StandingMode.CONSTANT,
            shape=AreaShape.SURFACE, point=None, axis=(1.0, 0.0),
            follows_owner=False, covered_id=None, affected=frozenset(),
            increments=None, interval_segments=None, established_at=0,
            established_seq=0, persistent=False, ended=False,
        )
    return dose(session, area, power, victim_id, dice=_roll(power, roller),
                distance_m=0.0, why=Dose.CONTACT, template=template,
                roller=roller)


# ---------------------------------------------------------------------------
# The menu: what a standing power is offered as
# ---------------------------------------------------------------------------

def standing_offers(session, actor_id: str, menu: list) -> list:
    """Take an always-on aura and a Damage Shield off the attack menu, and
    offer to raise a Damage Shield that is down.

    A Damage Shield is "a Constant Area Of Effect (personal Surface)" that
    "doesn't have to use an Attack Action to 'hit himself' ... he only has
    to use a Zero Phase Action to activate it" (6E1 p.323): it is never an
    attack on somebody else. A Persistent No Range aura is on all the time
    (6E1 p.130): using it as an attack again would land it twice.
    """
    from kirby_combat.enumeration import LegalAction

    actor = session.combatants[actor_id]
    kept = []
    for a in menu:
        power = getattr(a, "_attack_view", None)
        if power is not None and (is_personal_surface(power) or is_always_on(power)):
            continue
        kept.append(a)
    up = {a.power_source_id for a in damage_shields_on(session, actor_id)}
    for power in _views(actor):
        if not is_personal_surface(power) or is_always_on(power):
            continue
        if not getattr(power, "constant", False):
            continue
        from kirby_combat.power_modifiers import unbuilt_reasons

        if unbuilt_reasons(power) or not _slot_on(session, actor_id, power):
            continue
        source = str(getattr(power, "source_id", "") or "")
        if not source or source in up:
            continue
        kept.append(LegalAction(
            action_id=f"{RAISE_DAMAGE_SHIELD}:{source}",
            kind=RAISE_DAMAGE_SHIELD, target_id=None,
            power_xmlid=power.xmlid, power_name=power.name,
            summary=(f"Raise {power.name} --- a Damage Shield, a Zero Phase "
                     f"Action (6E1 p.323); it hurts whoever he hits or who "
                     f"hits him"),
            _attack_view=power,
        ))
    return kept


def raise_damage_shield(session, actor, power, *, template, roller):
    """Switch a Damage Shield on: pay its END (6E1 p.130's "costs END to
    activate") and write it down. Its first Phase's END is this one."""
    from kirby_combat.actions.recording import _spend_attack_end
    from kirby_combat.endurance import end_cost
    from kirby_combat.session.events import (
        ActionDeclared, ActionResolved, make_author_combatant,
    )

    now = datetime.now(timezone.utc)
    declared = ActionDeclared(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=now,
        author=make_author_combatant(actor.id), combatant_id=actor.id,
        action_type=RAISE_DAMAGE_SHIELD, targets=[actor.id],
        parameters={"power_xmlid": power.xmlid},
    )
    session = _apply(session, declared)
    session = _apply(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=now,
        author=make_author_combatant(actor.id),
        declaration_event_id=declared.id,
        result_payload={
            "kind": RAISE_DAMAGE_SHIELD, "target_id": actor.id, "hit": False,
            "stun_dealt": 0, "body_dealt": 0, "status_changes": [],
            "power_name": power.name, "power_xmlid": power.xmlid,
            "power_source_id": getattr(power, "source_id", None),
            "segment": session.timeline.segment,
        },
    ))
    session = _spend_attack_end(session, session.combatants[actor.id],
                                end_cost(power), template, power=power)
    return establish(session, owner_id=actor.id, power=power, point=None,
                     axis=(1.0, 0.0), covered_id=actor.id, affected=(),
                     use_event_id=declared.id)


def resolve_surface_use(session, attack, template, *, roller,
                        declaration_event_id, action_type, combat_type,
                        payload_extras):
    """A Surface laid on another man (6E1 p.323).

    "To use an Area Of Effect (Surface) power, a character must make an
    Attack Roll to hit the Surface ... another character has his standard
    DCV ... If the Attack Roll succeeds, the Surface has been 'covered' by
    the Power" --- and "any character who comes into contact with that
    Surface suffers the Power's effects immediately". The man it covers is
    in contact with it, so he suffers it now; Constant, "a character takes
    damage from it every Phase he remains in contact with it", which is the
    Constant attack `lingering.py` already maintains. Whoever touches him
    meanwhile is caught by `contact_doses`.

    So this is the ordinary attack at the door, at his DCV, with the Area
    taken off the shape that is rolled; the build's view keeps its Surface,
    and that is how the covered skin is found again (`covered_skins`).
    """
    from kirby_combat.actions.recording import resolve_attack_in_session

    if not getattr(attack.power, "is_ranged", False):
        raise ValueError(
            f"{getattr(attack.power, 'name', '?')!r} is a Damage Shield (a "
            "Surface with No Range, 6E1 p.323): it is raised, never fired; "
            "it should not have been offered as an attack")
    return resolve_attack_in_session(
        session, replace(attack, power=replace(attack.power, area=None)),
        template, declaration_event_id=declaration_event_id,
        action_type=action_type, roller=roller, combat_type=combat_type,
        payload_extras=payload_extras,
    )
