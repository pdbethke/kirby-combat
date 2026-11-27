"""What a wound does to a man: the lethality options a Gritty campaign turns on.

Western Hero's Gritty Campaign (book p.168) turns on every optional rule
that makes a gunshot dangerous. This module is the door for the ones that
follow from BODY taken, called by `recording.resolve_attack_in_session`
right after `impact.after_the_blow` and before the row, so the row can say
what the wound did.

**WOUNDING (6E2 p.110, `CombatTemplate.use_wounding`).** "A character who
takes BODY damage for any reason must make an EGO Roll at -1 for every full
2 BODY the character has taken. ... If the roll fails, the character can't
take any offensive action in his next Phase - he can't shoot, strike back,
or use any offensive Combat Maneuver. He may still move to Behind Cover,
Dodge, or use any other neutral or defensive Combat Maneuver."

  * RULING (Peter, 2026-11-27): the BODY is THIS hit's, not the running
    total.
  * A 3 always makes a Characteristic Roll and an 18 always fails it
    (6E1 p.57).
  * The flinch is read back off the log: a failed roll on a row, and no
    `PhaseSpent` of his since. Recorded rather than held, so a replay
    lands on the same menu.
  * WHAT IS OFFENSIVE is decided by an allow-list of what is not
    (`NON_OFFENSIVE_KINDS`), so an offer kind this module has never heard
    of is withheld rather than let through. Set and Hold are left out:
    Set is aiming and a Held Action waits to attack, and both are the
    offence the page takes away.

**IMPAIRING AND DISABLING (6E2 p.113-114, `use_impairing_disabling`, with
Hit Locations).** "Whenever the BODY damage done to an area ... is more than
half the character's total BODY, that area is Impaired"; more than his total
BODY, Disabled. The BODY is the hit's BODY taken, after defenses and the
location's BODYx (Western Hero p.154: "after defenses"). Effects in the
fight, from Western Hero's table (p.154), the campaign book these fights
run under:

  * HEAD: Knocked Out (to -10 STUN), and -2 to his CVs after.
  * HANDS, ARMS, SHOULDERS: -3 OCV with any attack made with that arm
    (6E2 p.113) --- a gun held in that hand, or in both (`grips`).
  * CHEST, STOMACH, VITALS: no Post-Segment 12 Recovery.
  * THIGHS, LEGS, FEET: -2 DCV and Running halved.

  RULING (Peter, 2026-11-27): head and torso effects only on a failed CON
  Roll (6E2 p.113: "The Impairment effect for head and torso areas should
  only occur if the character fails to make a CON Roll"), never outright
  death. Duration: 1d6 on the Impairment Table (1 Turn, 1 Minute, 5
  Minutes, 1 Hour, 5 Hours, 1 Day). A Disabling wound lasts the fight; its
  long-term result (6E2 p.114's tables) is recorded on the row, not
  applied here.

**WHICH ARM (rulings, Peter 2026-11-27).** 6E has no facing rule for a
person, and the Hit Location table names no side. A man stands BLADED
toward whoever he last attacked --- side-on, gun hand toward them, the
period one-handed stance --- and before he has attacked anyone, toward the
nearest enemy. A shot from his front half hits the side he presents, from
behind the other. The side he presents is the hand of the gun he last
attacked with (the first gun in his stated grips before he has fired);
``both`` for a two-handed gun, whose wound spoils it whichever arm it is.
With no map there is no behind: every shooter is in front of him.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

#: 6E2 p.110: -1 "for every full 2 BODY".
BODY_PER_POINT = 2

#: 6E1 p.57.
ALWAYS_MAKES, ALWAYS_FAILS = 3, 18

#: Neutral or defensive: what a flinching man may still do (6E2 p.110
#: names moving to cover and Dodge; "any other neutral or defensive Combat
#: Maneuver"). Movement, getting up, recovering, tending the dying and
#: getting out of a hold are neither offence nor attack.
NON_OFFENSIVE_KINDS = frozenset({
    "dodge", "block", "hide", "disengage", "move_to_cover", "reposition",
    "move", "half_move", "climb", "stand_up", "recover", "stabilize",
    "pickup", "pick_up_weapon", "no_abort",
    "escape_str", "escape_ego", "escape_teleport",
})

#: The row key the check is recorded under.
WOUNDING = "wounding"
#: The row key an Impairing or Disabling wound is recorded under.
WOUND = "wound"

HEAD, ARM, TORSO, LEG = "head", "arm", "torso", "leg"
#: 6E2 p.113's areas, by the Hit Location table's names (`tables`).
REGION = {
    "Head": HEAD,
    "Hand": ARM, "Arm": ARM, "Shoulder": ARM,
    "Chest": TORSO, "Stomach": TORSO, "Vitals": TORSO,
    "Thigh": LEG, "Leg": LEG, "Foot": LEG,
}
IMPAIRED, DISABLED = "impaired", "disabled"

#: 6E2 p.113's Impairment Table, 1d6 -> how long, in Segments (a Turn is
#: 12 Segments, 6E2 p.18). Everything past a Turn outlasts any fight.
IMPAIRMENT_SEGMENTS = {1: 12, 2: 60, 3: 300, 4: 3600, 5: 18000, 6: 86400}
IMPAIRMENT_LABEL = {1: "1 Turn", 2: "1 Minute", 3: "5 Minutes", 4: "1 Hour",
                    5: "5 Hours", 6: "1 Day"}
#: Western Hero p.154.
HEAD_KO_STUN = -10
HEAD_CV_DELTA = -2
ARM_OCV_DELTA = -3
LEG_DCV_DELTA = -2


def characteristic_roll_of(combatant: Any, characteristic: str) -> int:
    """His Characteristic Roll (9 + CHAR/5, rounded), from kirby-cost.

    The canon rounds; a local `9 + X // 5` truncates and disagrees on 16 of
    40 values (see `session.tie_rule`). A built character reads his sheet
    and his campaign's roll constants, as `perception.per_roll_target`
    does; a stat block reads `combat_stats()`, and has no default.
    """
    from kirby_cost.engine.rolls import characteristic_roll, roll_constants

    hero = getattr(combatant, "hero", None)
    if hero is not None:
        base, denominator = roll_constants(hero)
        value = hero.characteristic_value(characteristic.upper())
    else:
        base, denominator = roll_constants(None)
        value = getattr(combatant.combat_stats(), characteristic.lower())
    return characteristic_roll(value, base=base, denominator=denominator)


def wounding_target(combatant: Any, *, body_taken: int) -> int:
    """The EGO Roll a man makes after taking ``body_taken`` BODY (6E2 p.110)."""
    return characteristic_roll_of(combatant, "EGO") - int(body_taken) // BODY_PER_POINT


def _made(roll: int, needed: int) -> bool:
    if roll == ALWAYS_MAKES:
        return True
    if roll == ALWAYS_FAILS:
        return False
    return roll <= needed


def wounding_check(session: "CombatSession", target_id: str, body_taken: int, *,
                   roller) -> dict | None:
    """The EGO Roll, as the row records it; None when no BODY got through."""
    if body_taken <= 0 or target_id not in session.combatants:
        return None
    needed = wounding_target(session.combatants[target_id], body_taken=body_taken)
    roll = sum(roller.roll_dice(3, 6))
    return {"target_id": target_id, "roll": roll, "needed": needed,
            "flinched": not _made(roll, needed)}


def severity(body_taken: int, starting_body: int) -> str | None:
    """IMPAIRED over half his BODY, DISABLED over all of it (6E2 p.113)."""
    if body_taken > starting_body:
        return DISABLED
    if 2 * body_taken > starting_body:
        return IMPAIRED
    return None


def after_the_wound(session: "CombatSession", attack: Any, result: Any, *,
                    roller, template) -> tuple["CombatSession", dict]:
    """What the lethality options make of BODY taken. Payload keys for the row."""
    out: dict[str, Any] = {}
    target_id = attack.target.id
    body_taken = int(result.body_dealt or 0)
    if template.use_wounding:
        check = wounding_check(session, target_id, body_taken, roller=roller)
        if check is not None:
            out[WOUNDING] = check
    if template.use_impairing_disabling and result.location and body_taken > 0:
        session, wound = _wound(session, attack, result, roller=roller)
        if wound is not None:
            out[WOUND] = wound
            if template.use_knockdown:
                down = knockdown(session, wound, roller=roller)
                wound["knockdown"] = down
                if down["fell"]:
                    from kirby_combat.statuses import FELL

                    out[FELL] = [target_id]
    return session, out


def knockdown(session, wound: dict, *, roller) -> dict:
    """6E2 p.114: an Impairing wound is a DEX Roll or fall; Disabling, down.

    NOT BUILT: the 2m he must retreat (Impairing) and the 1m per BODY rolled
    over his starting BODY he falls back (Disabling). He goes down where he
    stands.
    """
    if wound["severity"] == DISABLED:
        return {"fell": True, "rolled": False}
    man = session.combatants[wound["target_id"]]
    needed = characteristic_roll_of(man, "DEX")
    roll = sum(roller.roll_dice(3, 6))
    return {"fell": not _made(roll, needed), "rolled": True, "roll": roll,
            "needed": needed}


def _wound(session, attack, result, *, roller):
    target_id = attack.target.id
    target = session.combatants[target_id]
    region = REGION.get(result.location)
    grade = severity(int(result.body_dealt), int(target.max_body))
    if region is None or grade is None:
        return session, None
    wound: dict[str, Any] = {
        "target_id": target_id, "location": result.location, "region": region,
        "severity": grade, "turn": session.timeline.turn,
        "segment": session.timeline.segment,
    }
    took = True
    if region in (HEAD, TORSO):
        needed = characteristic_roll_of(target, "CON")
        roll = sum(roller.roll_dice(3, 6))
        took = not _made(roll, needed)
        wound["con_roll"] = {"roll": roll, "needed": needed}
    wound["took_effect"] = took
    if grade == IMPAIRED:
        lasts = sum(roller.roll_dice(1, 6))
        wound["lasts_segments"] = IMPAIRMENT_SEGMENTS[lasts]
        wound["lasts"] = IMPAIRMENT_LABEL[lasts]
    else:
        wound["lasts_segments"] = None            # the fight, and after
        wound["lasts"] = "the fight (Disabled)"
    if region == ARM:
        wound["side"] = side_hit(session, target_id, attack.attacker.id)
    if took and region == HEAD:
        session = _knock_out(session, target_id, attack.attacker.id)
    return session, wound


def _knock_out(session, target_id: str, by_id: str):
    """Western Hero p.154's Head Impairment: Knocked Out, to -10 STUN.

    A `VitalsChanged` like every other change to a man, so a replay lands
    on the same STUN (`vitals.record_vitals_change`).
    """
    from kirby_combat.vitals import record_vitals_change

    man = session.combatants[target_id]
    if man.state.current_stun <= HEAD_KO_STUN:
        return session
    session, _ = record_vitals_change(
        session, target_id, stun=HEAD_KO_STUN - man.state.current_stun, body=0,
        reason="impairing", caused_by=by_id)
    return session


def flinching(session: "CombatSession", combatant_id: str) -> bool:
    """Whether a failed Wounding roll still takes his offence (6E2 p.110).

    From the last failed roll against him until he spends a Phase.
    """
    flinched = False
    for event in session.event_log:
        kind = getattr(event, "kind", "")
        if kind == "PhaseSpent" and getattr(event, "combatant_id", None) == combatant_id:
            flinched = False
            continue
        payload = getattr(event, "result_payload", None)
        if not isinstance(payload, dict):
            continue
        check = payload.get(WOUNDING)
        if check and check.get("target_id") == combatant_id and check.get("flinched"):
            flinched = True
    return flinched


def without_offence(menu: Iterable) -> list:
    """The menu a flinching man is offered: neutral and defensive only."""
    return [a for a in menu if a.kind in NON_OFFENSIVE_KINDS]


# ---------------------------------------------------------------------------
# Which arm: facing (rulings in the module docstring)
# ---------------------------------------------------------------------------

def _last_attack(session, combatant_id: str) -> dict | None:
    """His last attack row's payload: who at, and with which power."""
    mine: set[str] = set()
    last = None
    for event in session.event_log:
        kind = getattr(event, "kind", "")
        if kind == "ActionDeclared" and getattr(event, "combatant_id", "") == combatant_id:
            mine.add(event.id)
        elif kind == "ActionResolved" and getattr(event, "declaration_event_id", "") in mine:
            payload = getattr(event, "result_payload", None) or {}
            if payload.get("target_id") and "hit" in payload:
                last = payload
    return last


def _hands_of_power(session, owner_id: str, source_id) -> str | None:
    from kirby_combat.grips import grip_of
    from kirby_combat.weapons import accessible_foci

    for weapon in accessible_foci(session.combatants[owner_id]):
        if str(source_id) in weapon.power_ids:
            return grip_of(session, owner_id, weapon.weapon_id)
    return None


def presented_side(session, combatant_id: str) -> str | None:
    """The side he stands with toward his target: his gun hand."""
    from kirby_combat.grips import stated_grips

    last = _last_attack(session, combatant_id)
    if last is not None and last.get("power_source_id") is not None:
        hands = _hands_of_power(session, combatant_id, last["power_source_id"])
        if hands is not None:
            return hands
    from kirby_combat.grips import grip_of

    for weapon_id in stated_grips(session, combatant_id):
        hands = grip_of(session, combatant_id, weapon_id)
        if hands is not None:
            return hands
    return None


def _facing_toward(session, combatant_id: str) -> str | None:
    """Whom he faces: his last target, else the nearest enemy."""
    from kirby_combat.placement import position_of
    from kirby_combat.side import Side

    last = _last_attack(session, combatant_id)
    if last is not None and last["target_id"] in session.combatants:
        return last["target_id"]
    scene = session.scene
    here = position_of(scene, combatant_id)
    me = session.combatants[combatant_id]
    best = None
    for other in session.combatants.values():
        if other.id == combatant_id or not Side.of(me).hostile_to(Side.of(other)):
            continue
        there = position_of(scene, other.id)
        if there is None:
            continue
        d = (there.x - here.x) ** 2 + (there.y - here.y) ** 2
        if best is None or d < best[0]:
            best = (d, other.id)
    return best[1] if best else None


def side_hit(session, target_id: str, shooter_id: str) -> str | None:
    """The arm a hit from ``shooter_id`` lands on. None: he presents no gun."""
    from kirby_combat.grips import BOTH, LEFT, RIGHT
    from kirby_combat.placement import position_of

    presented = presented_side(session, target_id)
    if presented is None or presented == BOTH:
        return presented
    scene = getattr(session, "scene", None)
    toward = _facing_toward(session, target_id) if scene is not None else None
    if toward is None:
        return presented                     # no map: no behind
    here, faced, shooter = (position_of(scene, i) for i in (target_id, toward, shooter_id))
    if here is None or faced is None or shooter is None:
        return presented
    dot = ((faced.x - here.x) * (shooter.x - here.x)
           + (faced.y - here.y) * (shooter.y - here.y))
    if dot >= 0:
        return presented
    return LEFT if presented == RIGHT else RIGHT


# ---------------------------------------------------------------------------
# What his wounds do now, folded from the log
# ---------------------------------------------------------------------------

def active_wounds(session, combatant_id: str) -> list[dict]:
    """Every Impairing or Disabling wound on him that took effect and lasts."""
    now = (session.timeline.turn - 1) * 12 + session.timeline.segment
    out = []
    for event in session.event_log:
        payload = getattr(event, "result_payload", None)
        if not isinstance(payload, dict):
            continue
        wound = payload.get(WOUND)
        if not wound or wound.get("target_id") != combatant_id or not wound.get("took_effect"):
            continue
        lasts = wound.get("lasts_segments")
        began = (wound["turn"] - 1) * 12 + wound["segment"]
        if lasts is None or now - began < lasts:
            out.append(wound)
    return out


def arm_ocv_delta(session, attacker_id: str, power: Any) -> int:
    """-3 OCV for an attack with a weapon in an impaired arm (6E2 p.113)."""
    from kirby_combat.grips import BOTH

    sides = {w.get("side") for w in active_wounds(session, attacker_id)
             if w["region"] == ARM}
    if not sides:
        return 0
    source = getattr(power, "source_id", None)
    hands = _hands_of_power(session, attacker_id, source) if source is not None else None
    if hands is None:
        return 0
    if hands == BOTH or BOTH in sides or hands in sides:
        return ARM_OCV_DELTA
    return 0


def wound_cv_modifiers(session, combatant_id: str) -> dict[str, float]:
    """The flat CV deltas his wounds give: legs -2 DCV, head -2 CVs."""
    out: dict[str, float] = {}
    for wound in active_wounds(session, combatant_id):
        if wound["region"] == LEG:
            out["dcv_delta"] = out.get("dcv_delta", 0) + LEG_DCV_DELTA
        elif wound["region"] == HEAD:
            out["dcv_delta"] = out.get("dcv_delta", 0) + HEAD_CV_DELTA
            out["ocv_delta"] = out.get("ocv_delta", 0) + HEAD_CV_DELTA
    return out


def no_post_twelve_recovery(session, combatant_id: str) -> bool:
    """A torso wound: no Post-Segment 12 Recovery (6E2 p.113)."""
    return any(w["region"] == TORSO for w in active_wounds(session, combatant_id))
