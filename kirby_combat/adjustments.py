"""Adjustment Powers — what an Aid, a Drain or a Healing actually changes.

6E1 p.137: "The effects of Adjustment Powers are applied to the Active Points
of a Characteristic or Power. To determine the effect of an Adjustment Power
on a Characteristic, divide the points Adjusted by the Characteristic's cost
per point. Adjustment Powers that affect Characteristics affect abilities
derived from them (such as the lifting capacity of and damage caused by STR,
or the Skill Roll calculated from DEX)."

WHAT WAS WRONG (2026-10-26). `_resolve_aid` / `_resolve_drain` recorded every
Adjustment as ``stat="STUN"`` whatever the power was bought against, divided
the roll by 5 for every characteristic, and the only consumers that read the
fold were the CV path and the Stunning check. So a Drain DEX drained nothing,
an Aid STR raised no damage, a Drain SPD left the man his Phases, and a
Drain CON was the one Adjustment in the engine that worked --- by accident,
because nothing ever recorded one.

THE UNIT IS THE BOOK'S. `AdjustmentApplied.delta` is CHARACTER POINTS, signed
(6E1 p.169: "the Character Points rolled apply directly to the Active
Points"), and the fade/return of 5 Character Points per Turn (6E1 p.141)
comes off those points. The characteristic moves by whole increments of its
cost per point (6E1 p.140: "removing or adding less than the number of
Character Points required to buy 1 point of the Characteristic ... has no
effect. However, the target regains/loses the remainder ... at the usual
rate"), and the cost per point rides on the event, read off the target's own
build when it was applied, so a replay needs no build to read it from and a
campaign that reprices a characteristic in its `.hdt` changes the result.

EVERY CONSUMER, BY ONE DOOR. The folded value is projected onto the target's
``state.drains`` / ``state.aids`` by `apply_event` (see `project_onto`), and
`HeroCombatant.combat_stats()` already weighs those as Contributions on the
characteristic itself. Everything that reads a stat --- CV, the Stunning
check, SPD and so the Phase chart, STR and so a punch's dice, PD/ED and so
the damage that gets through --- reads the adjusted number without being
told about Adjustments at all. Until this module projected them, those two
dicts were written by nothing.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


# ---------------------------------------------------------------------------
# What an Adjustment Power is bought against
# ---------------------------------------------------------------------------

#: The names HD writes in an Adjustment Power's INPUT for a characteristic,
#: mapped to the characteristic's xmlid. Measured on the local corpus: both
#: the abbreviation ("DEX") and the word ("Endurance") occur.
_CHARACTERISTIC_NAMES = {
    "STR": "STR", "STRENGTH": "STR",
    "DEX": "DEX", "DEXTERITY": "DEX",
    "CON": "CON", "CONSTITUTION": "CON",
    "INT": "INT", "INTELLIGENCE": "INT",
    "EGO": "EGO",
    "PRE": "PRE", "PRESENCE": "PRE",
    "OCV": "OCV", "DCV": "DCV", "OMCV": "OMCV", "DMCV": "DMCV",
    "SPD": "SPD", "SPEED": "SPD",
    "PD": "PD", "ED": "ED",
    "REC": "REC", "RECOVERY": "REC",
    "END": "END", "ENDURANCE": "END",
    "BODY": "BODY", "STUN": "STUN",
}

#: 6E1 p.143: "the effect of any Adjustment Power that increases or decreases
#: any of the following is halved: any Defense Power; the Characteristics
#: CON, DCV, DMCV, PD, ED, REC, END, BODY, and STUN".
DEFENSIVE_CHARACTERISTICS = frozenset(
    {"CON", "DCV", "DMCV", "PD", "ED", "REC", "END", "BODY", "STUN"})

#: The expendable characteristics (6E1 p.137-138), and the vital each one's
#: CURRENT value lives in. Adjusting one moves the maximum AND the current
#: value; see `expendable_vital`.
_EXPENDABLE = {"STUN": "stun", "BODY": "body", "END": "end"}

#: The `HeroCombatStats` attribute each characteristic is read through ---
#: the keys `combat_stats()` weighs ``state.drains`` / ``state.aids`` by.
#: The inverse of `hero_view._CHARACTERISTIC_FOR_STAT`, and built from it so
#: the two cannot drift.
def _stat_attr(xmlid: str) -> str:
    from kirby_combat.hero_view import _CHARACTERISTIC_FOR_STAT

    for attr, x in _CHARACTERISTIC_FOR_STAT.items():
        if x == xmlid:
            return attr
    raise KeyError(f"no combat stat reads the characteristic {xmlid!r}")


#: Power targets this engine can adjust: an attack power's dice. Keyed by
#: what HD writes in INPUT, valued by the attack xmlids it names (6E1 p.140:
#: "a character cannot buy Drain Killing Attack and use it against either
#: HKA or RKA; he has to buy Drain HKA or Drain RKA").
_ATTACK_POWER_NAMES = {
    "BLAST": frozenset({"ENERGYBLAST"}), "ENERGYBLAST": frozenset({"ENERGYBLAST"}),
    "ENERGY BLAST": frozenset({"ENERGYBLAST"}),
    "HKA": frozenset({"HKA", "KILLINGATTACKHTH"}),
    "RKA": frozenset({"RKA", "KILLINGATTACKRANGED"}),
    "HA": frozenset({"HANDTOHANDATTACK", "HA"}),
    "HAND-TO-HAND ATTACK": frozenset({"HANDTOHANDATTACK", "HA"}),
    "HANDTOHANDATTACK": frozenset({"HANDTOHANDATTACK", "HA"}),
    "MENTAL BLAST": frozenset({"MENTALBLAST", "EGOATTACK"}),
    "MENTALBLAST": frozenset({"MENTALBLAST", "EGOATTACK"}),
}

_POWER_PREFIX = "POWER:"


@dataclass(frozen=True)
class AdjustedCharacteristic:
    """One characteristic an Adjustment Power is bought against."""

    xmlid: str

    @property
    def stat(self) -> str:
        """What `AdjustmentApplied.stat` records: the characteristic xmlid."""
        return self.xmlid

    @property
    def defensive(self) -> bool:
        return self.xmlid in DEFENSIVE_CHARACTERISTICS


@dataclass(frozen=True)
class AdjustedPower:
    """One specific power of the target's, by identity (6E1 p.137: "he has to
    specify exactly which Blast he's targeting"). Its dice move."""

    source_id: str

    @property
    def stat(self) -> str:
        return f"{_POWER_PREFIX}{self.source_id}"

    @property
    def defensive(self) -> bool:
        # Only attack powers are adjusted this way, and none is a Defense
        # Power (6E1 p.143's list).
        return False


def _tokens(text: str) -> list[str]:
    parts = re.split(r",|&|/|\bAND\b", text.upper())
    return [p.strip() for p in parts if p.strip()]


def characteristic_targets(power) -> tuple[AdjustedCharacteristic, ...] | None:
    """The characteristics this Adjustment Power is bought against, or None
    when what it names is not something this engine can adjust.

    TWO OR MORE AT ONCE (6E1 p.139) are built only with Expanded Effect,
    which applies the full roll to each. Without it the character divides
    the roll "in the defined ratio", and "He must do this when he buys the
    Power" --- the ratio lives in his notes, not in a field, so such a power
    is NOT BUILT here rather than split by a ratio nobody chose.
    """
    from kirby_combat.hero_view import _has_modifier

    text = (getattr(power, "input", None) or "").strip()
    if not text:
        return None
    names = _tokens(text)
    xmlids = [_CHARACTERISTIC_NAMES.get(n) for n in names]
    if not xmlids or any(x is None for x in xmlids):
        return None
    if len(xmlids) > 1 and not _has_modifier(power, "EXPANDEDEFFECT"):
        return None
    return tuple(AdjustedCharacteristic(x) for x in dict.fromkeys(xmlids))


def power_targets_on(power, target) -> tuple[AdjustedPower, ...]:
    """The target's powers this Adjustment Power can reach, one per power.

    Empty when the power is bought against something other than an attack
    power by its type (a special-effect group such as "Fire Powers" names
    no power this engine can identify, and is not built).
    """
    text = (getattr(power, "input", None) or "").strip().upper()
    xmlids = _ATTACK_POWER_NAMES.get(text)
    if not xmlids:
        return ()
    return tuple(
        AdjustedPower(str(a.source_id))
        for a in (getattr(target, "attacks", None) or [])
        if (a.xmlid or "").upper() in xmlids and a.source_id
    )


def is_power_stat(stat: str) -> bool:
    return stat.startswith(_POWER_PREFIX)


def power_stat_source(stat: str) -> str:
    return stat[len(_POWER_PREFIX):]


# ---------------------------------------------------------------------------
# The Effect Roll
# ---------------------------------------------------------------------------

def effect_dice(power) -> tuple[int, bool, int]:
    """(whole dice, half die, pips) of an Adjustment Power.

    The same reading of HD's levels and adders an attack's dice get
    (`hero_view._compute_damage_dice`): Bokor's Healing Powder is 3½d6 by a
    PLUSONEHALFDIE adder, his Stinging Nettle Powder 3d6+1 by a PLUSONEPIP.
    `_levels` read the bare levels and dropped both.
    """
    from kirby_combat.hero_view import _compute_damage_dice

    xmlid = (getattr(power, "xmlid", "") or "").upper()
    full, half, plus_one, minus_one = _compute_damage_dice(power, xmlid)
    return int(full), bool(half), (1 if plus_one else 0) - (1 if minus_one else 0)


def roll_effect(power, roller) -> int:
    """Roll an Adjustment Power and total it (6E1 p.169: "rolls the dice and
    counts the total, which represents the Character Points added").

    A ½d6 counts as 6E2 p.100 counts one: the face halved and rounded up.
    """
    from kirby_combat.resolution.damage import half_die_face

    full, half, pips = effect_dice(power)
    rolled = roller.roll_dice(full + (1 if half else 0))
    whole = rolled[:full]
    total = sum(whole) + (half_die_face(rolled[-1]) if half else 0) + pips
    return max(0, total)


def maximum_effect(power) -> int:
    """6E1 p.169: "The maximum effect of the Aid ... is the maximum that
    could be rolled on the dice (for example, 30 Character Points for an Aid
    5d6.)" The same bound applies to Healing (6E1 p.234)."""
    full, half, pips = effect_dice(power)
    return max(0, 6 * full + (3 if half else 0) + pips)


def halved_for(target, points: int) -> int:
    """6E1 p.143: half effect against a defensive characteristic --- "he
    would roll 6d6 and then halve the result". Halved rounding DOWN: the
    book gives no rounding for it, and 6E1 p.140 already throws away any
    part of an increment, so the smaller reading is the one consistent with
    "less than an increment has no effect". A RULING, recorded."""
    return int(points) // 2 if target.defensive else int(points)


# ---------------------------------------------------------------------------
# Cost per point
# ---------------------------------------------------------------------------

def cost_per_point(combatant, xmlid: str) -> float:
    """Character Points per point of ``xmlid`` on THIS combatant's build.

    Read off the build's own characteristic object (``LVLCOST / LVLVAL`` from
    the template it was costed under: DEX 2, SPD 10, STUN 1 per 2, END 1 per
    5), never a table here --- "cost = numbers", and a campaign that
    reprices a characteristic must reprice its Adjustments with it.

    RAISES when the build does not carry the characteristic: an Adjustment
    priced against a guess would put a wrong number on the log for good.
    """
    for c in getattr(getattr(combatant, "hero", None), "characteristics", None) or []:
        if (getattr(c, "xmlid", "") or "").upper() != xmlid:
            continue
        level_cost = float(getattr(c, "level_cost", 0) or 0)
        level_value = float(getattr(c, "level_value", 0) or 0)
        if level_cost > 0 and level_value > 0:
            return level_cost / level_value
        break
    raise ValueError(
        f"{getattr(combatant, 'id', combatant)!r} carries no cost per point for "
        f"{xmlid}: its build's {xmlid} characteristic has no LVLCOST/LVLVAL. "
        f"An Adjustment is priced off the target's own build (6E1 p.137)."
    )


def cost_per_die(attack) -> float:
    """Character Points per 1d6 of an attack power, Advantages included.

    6E1 p.139: "you must take the Advantages into account ... Since
    (5 x 1¼ = 6.25), it takes 6 Character Points to increase the Blast by
    1d6" --- which is the power's Active Points over its dice.
    """
    dice = float(attack.damage_dice) + (0.5 if attack.half_die else 0.0)
    if dice <= 0 or int(getattr(attack, "active_points", 0) or 0) <= 0:
        raise ValueError(
            f"attack {attack.source_id!r} has no Active Points per die to "
            f"adjust it by: {attack.active_points} AP over {dice}d6"
        )
    return float(attack.active_points) / dice


def points_for(character_points: int, per_point: float) -> int:
    """Whole increments moved by ``character_points`` (6E1 p.140), signed,
    truncated toward zero: "Aiding 3 Character Points' worth of DEX results
    in a gain of only 1 point of DEX"."""
    if per_point <= 0:
        raise ValueError(f"cost per point must be positive, got {per_point}")
    magnitude = math.floor(abs(int(character_points)) / per_point + 1e-9)
    return magnitude if character_points >= 0 else -magnitude


# ---------------------------------------------------------------------------
# The fold, and its projection onto the combatant
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LiveAdjustment:
    """The net Character Points on one (target, stat), and what one point
    of it costs."""

    stat: str
    character_points: int
    per_point: float

    @property
    def points(self) -> int:
        return points_for(self.character_points, self.per_point)


def live_adjustments(session: "CombatSession", combatant_id: str) -> list[LiveAdjustment]:
    """Every Adjustment in force on this combatant, one per stat.

    The per-stat total of its instances (`session.effects.adjustment_instances`,
    each of which fades on its own, 6E1 p.139): the increments a stat moves
    by are counted on that total, so "the remainder can be added to by
    another use of the Power later on" (6E1 p.140). An `AdjustmentApplied`
    with no ``cost_per_point`` was written before kirby-combat recorded one,
    always with ``stat="STUN"`` and read by nothing; it is kept in the log
    and still changes nothing.
    """
    from kirby_combat.session.effects import adjustment_instances

    net: dict[str, int] = {}
    per_point: dict[str, float] = {}
    for inst in adjustment_instances(session, combatant_id):
        if inst.cost_per_point <= 0:
            continue
        net[inst.stat] = net.get(inst.stat, 0) + inst.character_points
        per_point[inst.stat] = inst.cost_per_point
    return [LiveAdjustment(s, cp, per_point[s]) for s, cp in net.items() if cp]


def net_adjustment(session: "CombatSession", combatant_id: str, stat: str) -> int:
    """The live net Adjustment on one characteristic, in POINTS of it, signed.

    Case-insensitive on ``stat`` because the xmlid an Adjustment records
    ("DCV") and the CV key a caller works in ("dcv") are written differently
    in different parts of this engine.
    """
    want = (stat or "").upper()
    return sum(a.points for a in live_adjustments(session, combatant_id)
               if a.stat == want)


def effective_characteristic(
    session: "CombatSession", combatant_id: str, stat: str, base: int,
) -> int:
    """``base`` (an UNADJUSTED value) plus whatever Aid or Drain is live.

    FLOORED AT ZERO (6E1 p.137: a Drained characteristic "functions as if
    he had STR 0" however far into the negatives it was taken). Engine code
    reads `combat_stats()`, which already carries the Adjustment; this is
    for a caller holding a value from somewhere else.
    """
    return max(0, int(base) + net_adjustment(session, combatant_id, stat))


def adjusted_con(session: "CombatSession", combatant) -> int:
    """The CON a Stunning check should read (6E2 p.106).

    `combat_stats()` carries a Drained or Aided CON now (see `project_onto`),
    so this is the combatant's CON as the session holds him. Kept as the
    named door `actions/recording.py` and `mental/recording.py` ask.
    """
    current = session.combatants.get(combatant.id, combatant)
    return int(current.combat_stats().con)


def project_onto(session: "CombatSession", combatant_id: str) -> "CombatSession":
    """Write the folded Adjustments onto the combatant's ``state``.

    ``state.drains`` / ``state.aids`` hold POINTS, keyed by the stat
    attribute `combat_stats()` reads (``"dex"``, ``"str_"``,
    ``"max_stun"``), each a positive magnitude; ``state.adjusted_dice`` holds
    whole dice per attack power, signed. Rebuilt whole from the log every
    time an Adjustment event is applied, so the projection is never a
    running total that could drift from the record.
    """
    combatant = session.combatants.get(combatant_id)
    if combatant is None or not hasattr(combatant, "state"):
        return session
    drains: dict[str, int] = {}
    aids: dict[str, int] = {}
    dice: dict[str, int] = {}
    for live in live_adjustments(session, combatant_id):
        points = live.points
        if not points:
            continue
        if is_power_stat(live.stat):
            dice[power_stat_source(live.stat)] = points
            continue
        attr = _stat_attr(live.stat)
        if points > 0:
            aids[attr] = points
        else:
            drains[attr] = -points
    state = replace(combatant.state, drains=drains, aids=aids, adjusted_dice=dice)
    combatants = {**session.combatants, combatant_id: replace(combatant, state=state)}
    return replace(session, combatants=combatants)


def expendable_vital(xmlid: str) -> str | None:
    """The vital (``"stun"``/``"body"``/``"end"``) an expendable
    characteristic's current value lives in, or None for the rest."""
    return _EXPENDABLE.get(xmlid)


#: The CV keys `cv_modifiers._effective_cv` works in, mapped to the
#: characteristic xmlid an Adjustment would name. OCV and DCV are their own
#: characteristics in 6E and not abbreviations of something else.
CV_STATS = {"ocv": "OCV", "dcv": "DCV", "omcv": "OMCV", "dmcv": "DMCV"}
