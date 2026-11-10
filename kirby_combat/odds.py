"""What an attack is worth before it is rolled, under the rules.

The resolver answers "what did this roll do". A seat that chooses needs
"what will it do, on average", and that is the same rules asked over every
roll the dice can make --- so it lives here, beside the resolver, and asks
the resolver's own functions: `resolve_to_hit` / `resolve_mental_to_hit`
for each 3d6 total, `actions.autofire.burst_hits_on` for a burst's hits,
`resolution.damage_taken.damage_taken` (the attack door's damage step) for
each damage roll, `area_attack_roll` for an area, `Block.resolve` for a
Block.

LIFTED FROM kirby-ai (`kirby_ai/sim/ev.py`, `kirby_ai/reactions.py`,
2026-11-10). It sat there with its own "ENGINE GAP: kirby-combat ... owns no
probability" note, assembled the damage step from pieces and so missed the
Penetrating minimum, and priced a damage roll by its TOTAL, which is wrong
wherever the faces matter (a Normal attack's BODY, Penetrating's minimum).
Here every damage roll is a real roll: the joint distribution of (total,
Normal BODY) over the dice, one representative roll per pair.

PURE. Nothing here rolls a die, writes an event or touches a session's log.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

_FACES = (1, 2, 3, 4, 5, 6)


# ---------------------------------------------------------------------------
# The dice
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def sum_pmf(dice: int) -> tuple[tuple[int, float], ...]:
    """The exact distribution of the total of ``dice`` d6, as (total, p)."""
    pmf: dict[int, float] = {0: 1.0}
    for _ in range(max(0, dice)):
        rolled: dict[int, float] = {}
        for total, p in pmf.items():
            for face in _FACES:
                rolled[total + face] = rolled.get(total + face, 0.0) + p / 6.0
        pmf = rolled
    return tuple(sorted(pmf.items()))


def chance_of_rolling(at_most: int) -> float:
    """P(3d6 <= ``at_most``)."""
    return sum(p for total, p in sum_pmf(3) if total <= int(at_most))


def dice_totalling(count: int, total: int) -> list[int]:
    """``count`` faces summing to ``total``, for a question that reads only
    the total (an Attack Roll, a Skill Roll)."""
    faces = [1] * count
    left = total - count
    for i in range(count):
        take = min(5, left)
        faces[i] += take
        left -= take
        if left <= 0:
            break
    return faces


@lru_cache(maxsize=None)
def damage_rolls(dice: int) -> tuple[tuple[tuple[int, ...], float], ...]:
    """Every distinct (total, Normal BODY) ``dice`` d6 can show, as one real
    roll each with its probability.

    A damage roll is read by its total (Normal STUN, Killing BODY) and by
    its Normal BODY (0 for a 1, 1 for a 2-5, 2 for a 6: a Normal attack's
    BODY, and Penetrating's minimum, 6E1 p.344). Any two rolls agreeing on
    both read the same, so one stands for all of them.
    """
    from kirby_combat.resolution.damage import _body_for_normal_die

    states: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {(0, 0): (1.0, ())}
    for _ in range(max(0, dice)):
        nxt: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {}
        for (total, body), (p, roll) in states.items():
            for face in _FACES:
                key = (total + face, body + _body_for_normal_die(face))
                q, example = nxt.get(key, (0.0, roll + (face,)))
                nxt[key] = (q + p / 6.0, example)
        states = nxt
    return tuple((roll, p) for (p, roll) in sorted(states.values(), key=lambda v: v[1]))


# ---------------------------------------------------------------------------
# Hitting
# ---------------------------------------------------------------------------

def is_mental(power: Any) -> bool:
    """Whether the engine resolves this attack through mental combat: the
    power says so (`hero_view` writes "mental" off the build's own
    ``DEFENSE="MENTAL"``)."""
    return ((getattr(power, "damage_type", "") or "").lower() == "mental"
            or (getattr(power, "defense_type", "") or "").lower() == "mental")


def to_hit_by_roll(attacker: Any, target: Any, power: Any, *,
                   distance_m: float | None, template: Any,
                   dcv_modifier: int = 0, ocv_modifier: int = 0):
    """``(probability, the engine's to-hit answer)`` for every 3d6 total.

    Mental attacks go through `resolve_mental_to_hit`, which charges no
    Range Modifier (6E1 p.105) and on which a Dodge's DCV does nothing.
    """
    from kirby_combat.models import AttackInput, DiceValues
    from kirby_combat.resolution.to_hit import resolve_to_hit

    mental = is_mental(power)
    for total, weight in sum_pmf(3):
        faces = dice_totalling(3, total)
        if mental:
            from kirby_combat.mental import resolve_mental_to_hit

            result = resolve_mental_to_hit(attacker, target, faces,
                                           distance_m=distance_m)
        else:
            result = resolve_to_hit(
                AttackInput(attacker=attacker, target=target, power=power,
                            distance_m=distance_m, aim=None,
                            dice=DiceValues(to_hit=faces),
                            dcv_modifier=int(dcv_modifier),
                            ocv_modifier=int(ocv_modifier)),
                template)
        yield weight, result


def chance_to_hit(attacker: Any, target: Any, power: Any, *,
                  distance_m: float | None = None, template: Any,
                  dcv_modifier: int = 0, ocv_modifier: int = 0) -> float:
    """P(this attack hits him)."""
    return sum(w for w, r in to_hit_by_roll(
        attacker, target, power, distance_m=distance_m, template=template,
        dcv_modifier=dcv_modifier, ocv_modifier=ocv_modifier) if r.hit)


def expected_burst_hits(attacker: Any, target: Any, power: Any, shots: int, *,
                        distance_m: float | None = None, template: Any,
                        dcv_modifier: int = 0, ocv_modifier: int = 0) -> float:
    """The hits an Autofire burst of ``shots`` lands on him, on average (6E2
    p.44, by `burst_hits_on`)."""
    from kirby_combat.actions.autofire import burst_hits_on

    return sum(w * burst_hits_on(r, shots) for w, r in to_hit_by_roll(
        attacker, target, power, distance_m=distance_m, template=template,
        dcv_modifier=dcv_modifier, ocv_modifier=ocv_modifier))


# ---------------------------------------------------------------------------
# Damage
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Through:
    """What one hit puts through his defences, on average."""

    stun: float = 0.0
    body: float = 0.0


def average_through(power: Any, target: Any, template: Any) -> Through:
    """The mean STUN and BODY one hit gets through, over every roll, by the
    attack door's own damage step (`damage_taken`).

    NO HIT LOCATION: a location is rolled per shot, so a shot nobody has
    aimed is priced on the body as a whole (the no-location branch). A
    Killing attack's STUN Multiplier is rolled through the engine unless the
    template fixes it.
    """
    from kirby_combat.models import DiceValues
    from kirby_combat.resolution.damage_taken import damage_taken

    whole = int(getattr(power, "damage_dice", 0) or 0)
    half = bool(getattr(power, "half_die", False))
    if whole <= 0 and not half:
        return Through()
    killing = getattr(power, "damage_type", "") == "killing"
    half_faces = _FACES if half else (None,)
    mult_faces = (_FACES if killing
                  and getattr(template, "killing_stun_mult_fixed", None) is None
                  else (None,))
    stun = body = 0.0
    weight_each = 1.0 / (len(half_faces) * len(mult_faces))
    for roll, p in damage_rolls(whole):
        for h in half_faces:
            faces = list(roll) + ([h] if h is not None else [])
            for m in mult_faces:
                taken = damage_taken(power, target, DiceValues(
                    damage=faces, stun_multiplier=[m] if m is not None else []),
                    template)
                stun += p * weight_each * taken.stun
                body += p * weight_each * taken.body
    return Through(stun=stun, body=body)


@dataclass(frozen=True)
class Expected:
    """What an attack does to one man, on average, before it is rolled."""

    chance_to_hit: float
    hits: float
    stun: float
    body: float


def expected(attacker: Any, target: Any, power: Any, *, shots: int = 1,
             distance_m: float | None = None, template: Any,
             dcv_modifier: int = 0, ocv_modifier: int = 0) -> Expected:
    """P(hit), the hits (a burst of ``shots``, 6E2 p.44; 1 for one shot)
    and the STUN and BODY through his defences. Each Autofire hit is its own
    damage roll against them ("Each Autofire shot counts as a separate
    attack")."""
    kw = dict(distance_m=distance_m, template=template,
              dcv_modifier=dcv_modifier, ocv_modifier=ocv_modifier)
    chance = chance_to_hit(attacker, target, power, **kw)
    hits = (expected_burst_hits(attacker, target, power, shots, **kw)
            if shots > 1 else chance)
    if hits <= 0.0:
        return Expected(chance, 0.0, 0.0, 0.0)
    each = average_through(power, target, template)
    return Expected(chance, hits, hits * each.stun, hits * each.body)


def area_chance(session: Any, attacker: Any, named: Any, power: Any, *,
                template: Any) -> float:
    """P(an Area Of Effect use hits its point), by the engine's own roll
    against the point (6E1 p.321: DCV 3; DCV 0 within 2m or No Range)."""
    from kirby_combat.actions.area_attack import area_attack_roll
    from kirby_combat.models import AttackInput, DiceValues

    return sum(w for total, w in sum_pmf(3) if area_attack_roll(session, AttackInput(
        attacker=attacker, target=named, power=power, distance_m=None, aim=None,
        dice=DiceValues(to_hit=dice_totalling(3, total))), template).hit)


def expected_area(session: Any, attacker: Any, named: Any, target: Any,
                  power: Any, *, template: Any) -> Expected:
    """What an area aimed at ``named`` does to ``target``, on average.

    RULING: a hit on the point lands on him at full dice, a miss misses him.
    The engine moves a missed point (`area_attack._deviate`) and an
    Explosion loses dice with distance; neither is priced, so a man near the
    edge is priced as if at the centre.
    """
    chance = area_chance(session, attacker, named, power, template=template)
    if chance <= 0.0:
        return Expected(0.0, 0.0, 0.0, 0.0)
    each = average_through(power, target, template)
    return Expected(chance, chance, chance * each.stun, chance * each.body)


def block_chance(defender: Any, attacker: Any) -> float:
    """P(his Block succeeds) against ``attacker`` (6E2 p.59): his OCV with
    his own Block maneuver's OCV against the attacker's OCV."""
    from kirby_combat.actions.reactive.block import Block
    from kirby_combat.actions.reactive.martial import block_maneuver

    blocker = int(defender.combat_stats().ocv) + int(block_maneuver(defender).ocv)
    attacker_ocv = int(attacker.combat_stats().ocv)
    return sum(p for total, p in sum_pmf(3) if Block.resolve(
        blocker_ocv=blocker, blocker_dice=dice_totalling(3, total),
        attacker_ocv=attacker_ocv).success)


# ---------------------------------------------------------------------------
# Stunning (6E2 p.106) and Coordinated Attacks (6E2 p.46)
# ---------------------------------------------------------------------------

def stun_through_pmf(power: Any, target: Any, template: Any) -> tuple[tuple[int, float], ...]:
    """The distribution of STUN one hit gets through, as (stun, p), by the
    attack door's own damage step (`damage_taken`), over every roll."""
    from kirby_combat.models import DiceValues
    from kirby_combat.resolution.damage_taken import damage_taken

    whole = int(getattr(power, "damage_dice", 0) or 0)
    half = bool(getattr(power, "half_die", False))
    if whole <= 0 and not half:
        return ((0, 1.0),)
    killing = getattr(power, "damage_type", "") == "killing"
    half_faces = _FACES if half else (None,)
    mult_faces = (_FACES if killing
                  and getattr(template, "killing_stun_mult_fixed", None) is None
                  else (None,))
    each = 1.0 / (len(half_faces) * len(mult_faces))
    pmf: dict[int, float] = {}
    for roll, p in damage_rolls(whole):
        for h in half_faces:
            faces = list(roll) + ([h] if h is not None else [])
            for m in mult_faces:
                stun = damage_taken(power, target, DiceValues(
                    damage=faces, stun_multiplier=[m] if m is not None else []),
                    template).stun
                pmf[stun] = pmf.get(stun, 0.0) + p * each
    return tuple(sorted(pmf.items()))


def _convolve(a: dict[int, float], b: tuple[tuple[int, float], ...]) -> dict[int, float]:
    out: dict[int, float] = {}
    for x, p in a.items():
        for y, q in b:
            out[x + y] = out.get(x + y, 0.0) + p * q
    return out


def chance_to_stun(attacker: Any, target: Any, power: Any, *, con: int,
                   shots: int = 1, coordinated: bool = False,
                   already_pooled: int = 0, distance_m: float | None = None,
                   template: Any, dcv_modifier: int = 0,
                   ocv_modifier: int = 0) -> float:
    """P(this attack leaves him Stunned), before it is rolled.

    6E2 p.106: Stunned when the STUN one attack does after defences
    "exceeds his CON" (strictly greater, as `determine_status_changes`
    reads it). An Autofire hit is its own attack (6E2 p.44), so on its own a
    burst Stuns if any one hit does. COORDINATED (6E2 p.46) the strike is
    one attack: the STUN of every hit is added to what the window has
    already dealt him this Segment (``already_pooled``, the engine's
    `coordination.pooled_stun`) and the total is checked against CON ---
    the way the engine folds it. This is what makes several Penetrating or
    Armor Piercing attacks, each short of his CON, Stun a man together.
    """
    from kirby_combat.actions.autofire import burst_hits_on

    per_hit = stun_through_pmf(power, target, template)
    # Summed directly, not as 1 - P(<= CON): a roll that can never get past
    # CON is exactly 0, not 1 - 0.999...
    over_con = sum(p for s, p in per_hit if s > con)
    pooled_by_hits: dict[int, dict[int, float]] = {0: {0: 1.0}}

    def pooled(k: int) -> dict[int, float]:
        if k not in pooled_by_hits:
            pooled_by_hits[k] = _convolve(pooled(k - 1), per_hit)
        return pooled_by_hits[k]

    total = 0.0
    for weight, result in to_hit_by_roll(
            attacker, target, power, distance_m=distance_m, template=template,
            dcv_modifier=dcv_modifier, ocv_modifier=ocv_modifier):
        hits = burst_hits_on(result, shots) if shots > 1 else (1 if result.hit else 0)
        if hits <= 0:
            continue
        if coordinated:
            p = sum(q for s, q in pooled(hits).items() if already_pooled + s > con)
        else:
            p = 0.0 if over_con <= 0.0 else 1.0 - (1.0 - over_con) ** hits
        total += weight * p
    return total
