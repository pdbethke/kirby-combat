"""Grading a decision — the thing every measurement here has lacked.

`docs/gaps.md` ends on the admission that closes the loop on a week of
benchmarks: "It does not settle that the choices are GOOD ... nothing here
grades a decision as right or wrong." Coverage counts VARIETY -- how many
of 62 action kinds get chosen, which rule paths fire -- and a fighter who
spends the fight demolishing scenery scores as pleasing breadth.

THESE ONLY EVER SAY "WRONG". A Phase with no finding is not endorsed; it
is merely not indictable. Whether an attack was the BEST available choice
is judgement and this module has none. Whether it could not possibly have
worked is arithmetic, and arithmetic is what is here.

AND THEY GRADE DOCTRINE TOO. `TacticChooser` is graded by exactly the same
rules as anything else in the seat. A futile attack picked by doctrine is
an engine finding, not a chooser finding, and the only way to learn that
is to point the grader at both.

NO SECOND DAMAGE CALCULATION. Futility asks `compute_defense` and the
resolver's own `killing_damage` / `normal_damage` what a best-possible
roll gets through. Re-deriving "can this hurt him" here would drift from
the resolver silently, in the direction of whatever the rules last looked
like -- which is this repo's most expensive recurring defect, not a
hypothetical.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.loop.chooser import PhaseSituation

#: The kinds that put a power against a target and can therefore be futile.
_ATTACK_KINDS = frozenset({"attack", "strike", "move_strike", "move_through",
                           "haymaker", "rapid_fire", "multiple_attack"})

#: A best-possible d6. Futility is judged on the luckiest roll the dice can
#: produce, never an average: "usually does nothing" is a bad bet, and this
#: module indicts only what cannot work at all.
_BEST_DIE = 6

#: The best a killing attack's ½d6 STUN multiplier can return (6E2 p.100).
_BEST_STUN_MULT = 3


@dataclass(frozen=True)
class Finding:
    """One thing wrong with one decision.

    `kind` is the machine-readable label a report groups on; `why` is the
    sentence a person reads. Both, because a count of "futile: 14" tells
    you there is a problem and only the sentence tells you whose.
    """

    kind: str
    action_id: str
    why: str

    def render(self) -> str:
        return f"{self.kind}: {self.why}"


def critique(situation: "PhaseSituation", action_id: str) -> tuple[Finding, ...]:
    """Everything wrong with taking `action_id` in `situation`.

    Empty means nothing provable was wrong, NOT that the choice was good.

    Raises `KeyError` when the id is not on the menu. A grader that
    answered "no findings" for an id it never saw would report a clean
    sweep for a run whose ids it silently failed to match, which is the
    one result that must never be producible by accident.
    """
    action = next((a for a in situation.menu if a.action_id == action_id), None)
    if action is None:
        raise KeyError(
            f"{action_id!r} is not on this menu; the menu held "
            f"{len(situation.menu)} actions"
        )

    findings: list[Finding] = []
    for grade in (_futile, _scenery, _wasted):
        found = grade(situation, action)
        if found is not None:
            findings.append(found)
    return tuple(findings)


# ---------------------------------------------------------------------
# The graders
# ---------------------------------------------------------------------

def _futile(situation, action) -> Finding | None:
    """An attack whose BEST possible roll gets nothing through.

    Not "unlikely to hurt him" -- impossible to hurt him, on the luckiest
    roll the dice can produce, and therefore on every roll for the rest of
    the fight. Krackle's open defect list has carried this as "the AI's
    futile 1d6 blast" without anything able to count it.
    """
    power = getattr(action, "_attack_view", None)
    if action.kind not in _ATTACK_KINDS or power is None:
        return None
    target = _target_of(situation, action)
    if target is None:
        return None

    best = _best_case(power, target)
    if best is None or best != (0, 0):
        return None
    return Finding(
        kind="futile", action_id=action.action_id,
        why=(f"{power.name} cannot hurt {_name_of(target)} on its best "
             f"possible roll: 0 STUN and 0 BODY get through"),
    )


def _scenery(situation, action) -> Finding | None:
    """Shooting a wall while a man was on the menu.

    `PhaseSituation.ordered_menu` already names this exact case -- "the
    marshal of Tombstone spends his Phase shooting a house" -- and sorts
    scenery to the bottom to make it less likely. Ordering is a nudge;
    nothing recorded it when it happened anyway.

    NOT flagged when scenery is all there is. The engine's own words:
    "when a wall is all there is, a wall is what he hits."
    """
    if not getattr(action, "targets_construct", False):
        return None
    # AN OFFER ONLY COUNTS AS A MAN IF IT NAMES ONE. This first read
    # "any attack-kind offer that is not scenery", and reported three
    # Phases of doctrine shooting a house on the street benchmark. The
    # trace said otherwise: the only such offer was a `haymaker` with
    # `target_id=None`, a maneuver naming nobody, and the tactic that
    # fired was `smash_cover` -- whose basis is that "cover the enemy is
    # using is worth more destroyed than ignored", chosen with no shot at
    # a man on the menu at all. Doctrine was right and this was wrong.
    men = [a for a in situation.menu
           if not getattr(a, "targets_construct", False)
           and a.kind in _ATTACK_KINDS
           and a.target_id
           and _target_of(situation, a) is not None]
    if not men:
        return None
    return Finding(
        kind="scenery", action_id=action.action_id,
        why=(f"attacked terrain while {len(men)} offer(s) against a "
             f"combatant were on the menu"),
    )


def _wasted(situation, action) -> Finding | None:
    """A Phase spent buying something the actor already has.

    A Recover costs the whole Phase (6E2 p.58). At full STUN, BODY and END
    it buys nothing at all, and the actor stood still to buy it.
    """
    if action.kind != "recover":
        return None
    actor = situation.actor
    for current, most in (("current_stun", "max_stun"),
                          ("current_end", "max_end")):
        now = _vital(actor, current)
        cap = getattr(actor, most, None)
        if now is None or cap is None or now < cap:
            return None
    return Finding(
        kind="wasted", action_id=action.action_id,
        why="recovered at full STUN and END, which restores nothing",
    )


# ---------------------------------------------------------------------
# Reading the fight
# ---------------------------------------------------------------------

def _best_case(power, target) -> tuple[int, int] | None:
    """(STUN, BODY) through `target`'s defenses on the luckiest roll.

    Every number comes from the resolver's own functions. `None` when the
    engine declines to answer -- a power or target shaped in a way this
    cannot read is NOT evidence of futility, and must never be reported
    as such.
    """
    from kirby_combat.models import DiceValues
    from kirby_combat.resolution.damage import compute_damage
    from kirby_combat.resolution.defense import compute_defense
    from kirby_combat.resolution.hit_location import (
        LocationEffect, killing_damage, normal_damage,
    )
    from kirby_combat.template import DEFAULT_TEMPLATE

    dice_count = int(getattr(power, "damage_dice", 0) or 0)
    if dice_count <= 0:
        return None

    # NO HIT LOCATION. A location is rolled per shot and multiplies both
    # ways; grading against the best one would indict an attack that is
    # lethal to the head. The neutral body is the honest comparison.
    neutral = LocationEffect(name="", stun_x=1.0, normal_stun_x=1.0,
                             body_x=1.0, ocv_mod=0)
    rolled = [_BEST_DIE] * (dice_count + (1 if getattr(power, "half_die", False) else 0))
    dice = DiceValues(damage=rolled, stun_multiplier=[_BEST_STUN_MULT])

    # NARROW ON PURPOSE. A bare `except Exception` here turned a bug in
    # this function -- a template built wrong -- into "the engine declined
    # to answer", and the grader reported a clean sweep for an armoured
    # man being shot with 1d6. Only a target this cannot READ is excused;
    # anything else is a defect and must surface as one.
    if not hasattr(target, "combat_stats"):
        return None
    damage = compute_damage(power, dice, DEFAULT_TEMPLATE)
    defense = compute_defense(target, power)

    if getattr(power, "damage_type", "") == "killing":
        stun, body = killing_damage(
            damage.body, total_defense=defense.total_defense,
            resistant_defense=defense.resistant_defense, effect=neutral,
            stun_multiplier=int(damage.stun_multiplier or 1),
        )
    else:
        stun, body = normal_damage(
            damage.stun, damage.body, total_defense=defense.total_defense,
            effect=neutral,
        )
    return int(stun), int(body)


def _target_of(situation, action) -> Any | None:
    if not action.target_id:
        return None
    for who in list(situation.enemies) + list(situation.allies):
        if getattr(who, "id", None) == action.target_id:
            return who
    return None


def _name_of(who) -> str:
    return getattr(who, "name", None) or getattr(who, "id", "the target")


def _vital(actor, field: str) -> int | None:
    """A current vital, from the actor or its state.

    Both are read because both are populated in this codebase and neither
    is universal -- `PhaseSituation`'s own test doubles carry the pair for
    exactly that reason.
    """
    state = getattr(actor, "state", None)
    for holder in (state, actor):
        value = getattr(holder, field, None)
        if value is not None:
            return int(value)
    return None
