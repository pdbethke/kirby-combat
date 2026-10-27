"""Bodies moving: Knockback applied, falls, footing, and what hitting things costs.

PORTED FROM THE DELETED kirby-api DRIVER (its combat driver before 70ad60f:
``_apply_knockback``, ``_apply_falling_damage``, ``_maybe_lose_footing``),
which was the only thing that ever moved a man an attack had knocked back.
When the driver went, `resolve_knockback_movement` and `resolve_fall`
survived with no caller but their own tests: a Blast computed a Knockback
distance, logged it inside an audit string, and the target did not move,
did not hit the wall behind him and did not go down.

Each rule below is checked against the book as it came across; where the
driver was wrong it is corrected here and the correction is named.

WHAT THIS MODULE WRITES. No new event kind. A forced move is a
``MovementResolved`` (``move_type`` "knockback", "fall", "thrown"); the
STUN and BODY an impact costs is a ``VitalsChanged`` (``reason``
"knockback", "falling", "thrown"); who ended up on the ground is the
``statuses.FELL`` list on the ``ActionResolved`` row of the action that
put him there, which ``statuses._is_prone`` already folds. Every function
returns the payload it wants on that row and leaves building the row to
its caller, because nothing edits a committed row.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from kirby_combat.models import AttackPower, DiceValues

if TYPE_CHECKING:
    from kirby_world.scene import Position

    from kirby_combat.models import AttackInput, AttackResult
    from kirby_combat.session.combat_session import CombatSession


#: The skills this module asks for, by the xmlid the cost engine writes.
BREAKFALL = "BREAKFALL"
ACROBATICS = "ACROBATICS"


# ---------------------------------------------------------------------------
# Small shared pieces
# ---------------------------------------------------------------------------

def impact_power(dice: int, name: str) -> AttackPower:
    """The synthetic Normal Damage attack an impact is resolved as.

    6E2 p.118: Knockback damage is "1d6 Normal Damage"; 6E2 p.142:
    "Falling damage is usually physical Normal Damage". So a normal attack
    against PD, which no Knockback of its own (a landing does not knock
    anybody further).
    """
    return AttackPower(
        xmlid="IMPACT", name=name, damage_dice=int(dice), half_die=False,
        plus_one=False, damage_type="normal", defense_type="pd", range_m=0.0,
        uses_str=False, str_min=0, armor_piercing=0, penetrating=0,
        increased_stun_mult=0, no_knockback=True,
    )


def _position_of(session, combatant_id: str):
    scene = getattr(session, "scene", None)
    if scene is None:
        return None
    return (getattr(scene, "combatant_positions", None) or {}).get(combatant_id)


def _gravity(scene) -> float:
    """The scene's gravity, which scales falling (`kirby_world.resolve_fall`).

    Required, not defaulted: a Scene always carries `AmbientConditions`
    and its `gravity_scale`."""
    return float(scene.ambient.gravity_scale)


def is_airborne(session, combatant_id: str) -> bool:
    """Is this man in the air -- standing on nothing -- where he is now?

    RULING: the engine has no "flying" flag. A combatant the Scene puts at
    a height with no supporting surface under him got there by Flight or a
    leap (`movement_reach` only lands a mover unsupported for those), so
    he is in the air for 6E2 p.117's -1d6 and p.118's "hits nothing, takes
    no damage". A fight with no Scene has no air to be in.
    """
    from kirby_world.falling import is_supported_at

    pos = _position_of(session, combatant_id)
    if pos is None:
        return False
    return not is_supported_at(pos, session.scene)


def _record_move(session, combatant_id: str, start, end, *, move_type: str,
                 distance_m: float):
    """One forced move, as the one row that moves anybody."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import MovementResolved, make_author_engine

    if (start.x, start.y, start.z) == (end.x, end.y, end.z):
        return session
    return apply_event(session, MovementResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id=combatant_id,
        from_pos={"x": start.x, "y": start.y, "z": start.z, "facing": start.facing},
        to_pos={"x": end.x, "y": end.y, "z": end.z, "facing": end.facing},
        velocity_mps=float(distance_m), move_type=move_type,
    ))


def can_save(session, combatant_id: str) -> bool:
    """6E2 p.119: Breakfall against Knockback needs a man "not unconscious or
    Stunned". RULING: the same bar for every save in this module -- a man who
    is out cannot roll to land well, and that is the driver's bar too."""
    from kirby_combat.statuses import KNOCKED_OUT, STUNNED, statuses_for

    held = statuses_for(session, combatant_id)
    if STUNNED in held or KNOCKED_OUT in held:
        return False
    combatant = session.combatants[combatant_id]
    return int(combatant.state.current_stun) > 0


def _dice(roller):
    """The roller, or a refusal naming it. Nothing here invents dice."""
    if roller is None:
        raise ValueError(
            "a roll is owed (Knockback, a fall or a footing check) and no "
            "roller was given: pass roller= or set CombatSession.dice_roller")
    return roller


def skill_roll(session, combatant_id: str, xmlid: str, *, modifier: int,
               roller) -> dict | None:
    """Roll one of this man's skills at ``modifier``, or None if he has none.

    None is not a failed roll: "there was nothing to roll" and "the roll
    was lost" are different facts in the log (the same distinction
    ``resolvers._acrobatics_save`` records).
    """
    combatant = session.combatants[combatant_id]
    if not hasattr(combatant, "skill_roll_value"):
        return None
    base = combatant.skill_roll_value(xmlid)
    if base is None:
        return None
    needed = int(base) + int(modifier)
    rolled = sum(_dice(roller).roll_dice(3))
    return {"skill": xmlid, "target": needed, "roll": rolled,
            "made": rolled <= needed, "made_by": needed - rolled}


def impact_damage(session, target_id: str, dice: int, *, roller, template,
                  reason: str, double_stun: bool,
                  halved: bool) -> tuple["CombatSession", dict]:
    """Roll ``dice`` of Normal Damage against the target's PD and take it.

    The same damage and defense functions every attack uses, so Damage
    Reduction, Hardened and the rest apply exactly as they would to a
    punch. ``double_stun`` is 6E2 p.108: the Knockback damage from the
    attack that Knocked him Out does 2x STUN.

    Returns the session and a payload, which carries `stunned` when this
    damage on its own beat his CON (each instance of damage is checked on
    its own, 6E2 p.105). ``halved`` is a save that halves the damage TAKEN
    (6E1 p.68's Breakfall against a fall), applied after defenses.
    """
    from kirby_combat.adjustments import adjusted_con
    from kirby_combat.resolution.damage import compute_damage, stun_for_body_taken
    from kirby_combat.resolution.defense import compute_defense
    from kirby_combat.vitals import record_vitals_change

    if dice <= 0:
        return session, {"dice": 0, "stun_dealt": 0, "body_dealt": 0,
                         "stunned": False}
    target = session.combatants[target_id]
    power = impact_power(dice, reason)
    rolled = DiceValues(damage=_dice(roller).roll_dice(int(dice)))
    damage = compute_damage(power, rolled, template)
    defense = compute_defense(target, power)
    raw_stun = damage.stun * (2 if double_stun else 1)
    stun_dealt = max(0, raw_stun - defense.total_defense)
    body_dealt = max(0, damage.body - defense.total_defense)
    if defense.damage_reduction_pct > 0:
        mult = (100 - defense.damage_reduction_pct) / 100.0
        stun_dealt = int(stun_dealt * mult)
        body_dealt = int(body_dealt * mult)
    if halved:
        stun_dealt //= 2
        body_dealt //= 2
    stun_dealt = stun_for_body_taken(stun_dealt, body_dealt)   # 6E2 p.105
    session, _ = record_vitals_change(
        session, target_id, stun=-stun_dealt, body=-body_dealt, reason=reason,
    )
    return session, {
        "dice": int(dice), "dice_rolled": list(rolled.damage),
        "raw_stun": raw_stun, "raw_body": damage.body,
        "defense": defense.total_defense, "doubled_stun": bool(double_stun),
        "halved": bool(halved),
        "stun_dealt": stun_dealt, "body_dealt": body_dealt,
        "stunned": stun_dealt > adjusted_con(session, target),
    }


# ---------------------------------------------------------------------------
# Falling (6E2 p.142, 6E1 p.68)
# ---------------------------------------------------------------------------

def fall(session, combatant_id: str, from_pos: "Position", *, roller, template,
         landing=None) -> tuple["CombatSession", dict]:
    """He falls from ``from_pos`` to whatever is below and takes the damage.

    6E2 p.142: "A character who falls 20m or less takes 1d6 damage per full
    2m fallen" -- `kirby_world.resolve_fall` finds the surface and the dice.
    6E1 p.68, Breakfall: "Each 4m (or fraction thereof) the character falls
    imposes a -1 penalty on the roll. If the character succeeds with his
    Breakfall roll by half (after applying the height modifier), he takes no
    damage at all"; otherwise a success halves it. The driver applied full
    damage to everybody; the save is new here.

    ``landing`` is an already-resolved `FallingResult` (a forced move finds
    the fall itself); None asks `resolve_fall`.

    He lands PRONE: Breakfall's first use (6E1 p.68) is standing up "from
    falling" without a Half Phase, so a fall leaves him down. The caller
    puts him in its row's `statuses.FELL`.
    """
    from kirby_world.falling import resolve_fall

    scene = session.scene
    if landing is None:
        landing = resolve_fall(combatant_id=combatant_id, from_pos=from_pos,
                               scene=scene, gravity_scale=_gravity(scene))
    session = _record_move(session, combatant_id, from_pos, landing.landed_at,
                           move_type="fall", distance_m=landing.fall_distance_m)
    dice = int(landing.damage_dice)
    save = None
    if dice > 0 and can_save(session, combatant_id):
        penalty = -math.ceil(max(0.0, landing.fall_distance_m) / 4.0)
        save = skill_roll(session, combatant_id, BREAKFALL,
                          modifier=penalty, roller=roller)
    taken, halved = dice, False
    if save is not None and save["made"]:
        # "Succeeds by half": made by at least half of what he needed.
        # Otherwise "only half damage", read as half the damage TAKEN, the
        # same reading as the Thrown character's Breakfall (6E2 p.85).
        if save["made_by"] * 2 >= save["target"]:
            taken = 0
        else:
            halved = True
    session, damage = impact_damage(
        session, combatant_id, taken, roller=roller, template=template,
        reason="falling", double_stun=False, halved=halved,
    )
    return session, {
        "from_z": from_pos.z, "landed_z": landing.landed_at.z,
        "fall_distance_m": landing.fall_distance_m, "damage_dice": dice,
        "breakfall": save, **damage,
    }


# ---------------------------------------------------------------------------
# Knockback (6E2 p.116-119)
# ---------------------------------------------------------------------------

def knockback_dice_for(session, attack: "AttackInput", template) -> int:
    """How many d6 the attacker subtracts from the BODY (6E2 p.117's table).

    2d6, +1d6 for a Killing attack, +1d6 for a Martial Maneuver, -1d6 for a
    target in the air, -1d6 in zero gravity; "the modifiers are
    cumulative". 0 when this attack can do no Knockback, so nothing is
    rolled for it.

    NOT BUILT: Rolled With The Punch (-1d6), underwater (+1d6), Clinging
    (+1d6): the engine has no record of any of them.
    """
    from kirby_combat.resolution.knockback import does_knockback

    if not template.use_knockback or not does_knockback(attack.power):
        return 0
    count = 2
    if attack.power.damage_type == "killing":
        count += 1
    if attack.power.xmlid == "MANEUVER":
        count += 1
    target_id = getattr(attack.target, "id", None)
    if target_id in session.combatants and is_airborne(session, target_id):
        count -= 1
    scene = getattr(session, "scene", None)
    if scene is not None and _gravity(scene) == 0.0:
        count -= 1
    return max(0, count)


def apply_knockback(session, attack: "AttackInput", result: "AttackResult", *,
                    roller, template) -> tuple["CombatSession", dict | None, list[str]]:
    """Move the man an attack knocked back, hurt him, and put him down.

    Returns ``(session, payload, fell)``: the payload for the attack's row
    (None when there was no Knockback to apply) and the ids who ended on
    the ground, for its `statuses.FELL`.

    The distance is the pure resolver's (`result.knockback`, 6E2 p.116).
    What happens to him (6E2 p.118-119):

    - He travels away from the attacker until something stops him
      (`resolve_forced_movement`). With no Scene he goes nowhere, but he
      still hits the ground.
    - INTO A WALL: 1d6 per full 2m of the WHOLE distance rolled ("there's
      no deceleration"), at most the wall's PD + BODY. Breakfall cannot
      help. A wall authored with no DEF is uncapped (RULING).
    - OFF AN EDGE: he falls, and takes falling damage INSTEAD of the 1d6
      per 4m for hitting the ground (RULING, on p.118's "the GM may ...
      apply falling damage instead"). The driver charged him both.
    - IN THE AIR, hitting nothing: no damage at all (p.118), and he is not
      Prone -- he is lying on nothing (RULING; the Half Phase to reorient
      is not modelled).
    - OTHERWISE he hits the ground: 1d6 per 4m, unless a Breakfall at -1
      per 4m (or fraction) lands him on his feet with no damage (p.119).
    - KNOCKED DOWN (BODY - roll = 0): no distance and no damage, but he is
      on the ground (p.116); Breakfall at no penalty keeps his feet (6E1
      p.68).

    He ends Prone unless Breakfall saved him (p.116: "He ends up lying on
    the ground ... and must spend a Half Phase to get up"). The driver set
    nobody prone.

    NOT BUILT, and named: a structure shattered by Knockback (more than
    2x its PD + BODY) lets him "continue through the hole" -- here he stops
    at it, takes its PD + BODY dice, and the structure takes no damage.
    """
    from kirby_combat.actions.movement.knockback_movement import (
        away_from,
        resolve_forced_movement,
    )
    from kirby_combat.resolution.knockback import (
        ImpactTarget,
        compute_impact_damage_dice,
    )

    kb = result.knockback
    if not result.hit or kb is None:
        return session, None, []
    target_id = attack.target.id
    attacker_id = attack.attacker.id
    if target_id not in session.combatants:
        return session, None, []
    meters = float(kb.distance_m)
    if meters <= 0 and not kb.knocked_down:
        return session, None, []

    payload: dict[str, Any] = {
        "distance_m": meters, "knocked_down": bool(kb.knocked_down),
        "dice": kb.dice,
    }
    # 6E2 p.108: Knockback damage from the attack that Knocked him Out
    # does 2x STUN.
    double_stun = "Knocked Out" in (result.status_changes or [])

    if kb.knocked_down:
        save = (skill_roll(session, target_id, BREAKFALL, modifier=0, roller=roller)
                if can_save(session, target_id) else None)
        payload["breakfall"] = save
        on_feet = save is not None and save["made"]
        payload["prone"] = not on_feet
        return session, payload, ([] if on_feet else [target_id])

    start = _position_of(session, target_id)
    source = _position_of(session, attacker_id)
    airborne = is_airborne(session, target_id)
    moved = None
    if start is not None and source is not None:
        moved = resolve_forced_movement(
            combatant_id=target_id, start=start,
            direction_xy=away_from(source, start), distance_m=meters,
            scene=session.scene, gravity_scale=_gravity(session.scene),
            airborne=airborne,
        )
        session = _record_move(session, target_id, start, moved.travel_end,
                               move_type="knockback",
                               distance_m=moved.distance_traveled_m)
        payload["from"] = [start.x, start.y, start.z]
        payload["to"] = [moved.travel_end.x, moved.travel_end.y, moved.travel_end.z]

    fell = [target_id]
    if moved is not None and moved.wall_collision is not None:
        wall = moved.wall_collision
        if wall.pd is None:
            dice = int(meters) // 2
        else:
            dice, _through = compute_impact_damage_dice(
                meters, ImpactTarget(pd=int(wall.pd), body=int(wall.body),
                                     breakable=True))
        payload["wall_id"] = wall.wall_id
        session, payload["impact"] = impact_damage(
            session, target_id, dice, roller=roller, template=template,
            reason="knockback", double_stun=double_stun,
            halved=False,
        )
    elif moved is not None and moved.fall is not None:
        session, payload["fall"] = fall(
            session, target_id, moved.travel_end, roller=roller,
            template=template, landing=moved.fall,
        )
    elif airborne:
        fell = []
    else:
        save = None
        if can_save(session, target_id):
            save = skill_roll(session, target_id, BREAKFALL,
                              modifier=-math.ceil(meters / 4.0), roller=roller)
        payload["breakfall"] = save
        if save is not None and save["made"]:
            fell = []
        else:
            session, payload["impact"] = impact_damage(
                session, target_id, int(meters) // 4, roller=roller,
                template=template, reason="knockback", double_stun=double_stun,
                halved=False,
            )
    payload["prone"] = bool(fell)
    return session, payload, fell


# ---------------------------------------------------------------------------
# Footing on a narrow perch
# ---------------------------------------------------------------------------

def precarious_under(session, combatant_id: str) -> bool:
    """Is he standing on a surface flagged narrow footing (a ledge, a wall
    top, a tightrope)? `kirby_world.Surface.is_precarious`."""
    from kirby_world.geometry import point_in_polygon_xy

    pos = _position_of(session, combatant_id)
    if pos is None:
        return False
    for surf in session.scene.supporting_surfaces():
        if not surf.is_supporting or not surf.is_precarious:
            continue
        if abs(surf.elevation_m - pos.z) > 1e-6:
            continue
        if point_in_polygon_xy((pos.x, pos.y), surf.polygon_xy):
            return True
    return False


def keep_footing(session, target_id: str, result: "AttackResult", *, roller,
                 template) -> tuple["CombatSession", dict | None, list[str]]:
    """A man hit while standing on a narrow perch may lose his footing.

    GM RULING, ported from the driver (supported-vantages spec §5): the
    book prices standing on a ledge (6E2 p.39, -2 DCV on a narrow surface)
    and says how to keep one's balance there (6E1 p.65, Acrobatics "can
    also retain his balance when walking on narrow or difficult surfaces";
    6E1 p.15, "a DEX Roll to walk along a narrow beam"), and leaves when a
    roll is called for to the GM. This engine calls for one when an attack
    hits him there. Stunned, Knocked Out or already Prone, he cannot keep
    his feet.

    The roll is the better of his DEX Roll (9 + DEX/5) and Acrobatics.
    CORRECTED from the driver, which also let Breakfall count: Breakfall's
    footing use is "soft or slippery surfaces, such as ice, wet stone, mud"
    (6E1 p.68), which a ledge is not.

    On a failure he falls from the perch (`fall`) and ends Prone.
    """
    from kirby_combat.statuses import PRONE, statuses_for

    if not result.hit or target_id not in session.combatants:
        return session, None, []
    if getattr(session, "scene", None) is None or not precarious_under(session, target_id):
        return session, None, []
    status = list(result.status_changes or [])
    stunned = "Stunned" in status or "Knocked Out" in status or not can_save(session, target_id)
    prone = PRONE in statuses_for(session, target_id)
    payload: dict[str, Any] = {"reason": "stunned" if stunned else ("prone" if prone else "damage")}
    if stunned or prone:
        payload.update({"rolled": False, "kept_footing": False})
    else:
        combatant = session.combatants[target_id]
        best = 9 + int(combatant.combat_stats().dex) // 5
        acro = (combatant.skill_roll_value(ACROBATICS)
                if hasattr(combatant, "skill_roll_value") else None)
        if acro is not None and int(acro) > best:
            best = int(acro)
        rolled = sum(_dice(roller).roll_dice(3))
        payload.update({"rolled": True, "target": best, "roll": rolled,
                        "kept_footing": rolled <= best})
    if payload["kept_footing"]:
        return session, payload, []
    pos = _position_of(session, target_id)
    session, payload["fall"] = fall(session, target_id, pos, roller=roller,
                                    template=template)
    return session, payload, [target_id]


# ---------------------------------------------------------------------------
# The door: what happens to a man after a blow lands
# ---------------------------------------------------------------------------

def after_the_blow(session, attack: "AttackInput", result: "AttackResult", *,
                   roller, template) -> tuple["CombatSession", dict]:
    """Knockback, then -- if it did not already take him off it -- footing.

    Called by `recording.resolve_attack_in_session`, the door every attack
    on a person goes through, AFTER the damage and BEFORE the row that
    describes the exchange, so that row can say where he went and that he
    went down. Returns the payload keys for that row (`knockback`,
    `footing`, and `statuses.FELL`), empty when nothing happened.

    The footing check is skipped when Knockback has already moved him or
    put him down: rolling to keep your feet on a ledge you have just been
    knocked off double-counts one event (the driver's reasoning, kept).
    """
    from kirby_combat.statuses import FELL

    out: dict[str, Any] = {}
    fell: list[str] = []
    session, kb, kb_fell = apply_knockback(
        session, attack, result, roller=roller, template=template)
    if kb is not None:
        out["knockback"] = kb
        fell += kb_fell
    moved = kb is not None and (kb.get("distance_m", 0) > 0 or kb.get("prone"))
    if not moved:
        session, footing, footing_fell = keep_footing(
            session, attack.target.id, result, roller=roller, template=template)
        if footing is not None:
            out["footing"] = footing
            fell += footing_fell
    if fell:
        out[FELL] = sorted(set(fell))
    return session, out
