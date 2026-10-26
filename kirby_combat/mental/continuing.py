"""Continuing-effect Mental Powers --- what is still in force, and breaking out.

6E1 p.150 calls Mental Illusions, Mind Control, Mind Link and Telepathy
"continuing-effect Mental Powers, since their effects continue beyond the
Phase in which a character makes an attack with them"; a Mind Scan lock-on is
broken out of "in the usual manner" (p.265). This module holds the two this
engine gives a lasting effect: **Mind Control** (an order the target obeys)
and a **Mind Scan lock** (mental line of sight to a mind the scanner cannot
see).

THE EFFECT IS THE ``ActionResolved`` THAT ESTABLISHED IT. Its payload already
says who did what to whom with which order; a second "effect applied" event
would be a second statement of the same fact. This folds the payloads forward
exactly as `framework.active_slots` folds ``reallocate`` --- and the one thing
an action record cannot say, the Breakout Rolls the target makes on his own
Phases, is its own event, `BreakoutRolled`.

**The Breakout Roll** (6E1 p.151-152, p.258). "Starting on the target's next
Phase after being successfully attacked ... he may attempt to break free ...
These attempts are subconscious and take no time --- whether he succeeds or
fails, he may still act in that Phase", and "a character always gets one (but
only one) Breakout Roll before he suffers the effects". It is an EGO Roll at
-1 per 5 points the effect beat its minimum; after the first, "the victim can
re-attempt the Breakout Roll at +1 for each step on the Time Chart. The
character thus gets to roll at +1 after 1 Turn has passed, +2 after 1 Minute
has passed, and so forth. (The victim does not get to make a Breakout Roll on
each of his Phases --- only when specified by the Time Chart.)"

RULING: nobody pays END to stop the effect deteriorating (p.152). The engine
has no such action, so the Time Chart bonus always accrues.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

#: The kinds whose established result is a continuing effect.
CONTINUING_KINDS = frozenset({"mind_control", "mind_scan"})

#: Segments in a Turn (6E2 p.18).
_SEGMENTS_PER_TURN = 12

#: The Time Chart steps after the first Breakout attempt, in Turns, each with
#: the bonus it brings (6E1 p.152; the Time Chart, 6E2 p.27): 1 Turn, 1
#: Minute (5 Turns), 5 Minutes, 20 Minutes, 1 Hour.
_TIME_CHART_TURNS: tuple[tuple[int, int], ...] = (
    (1, 1), (5, 2), (25, 3), (100, 4), (300, 5),
)


@dataclass(frozen=True)
class BreakoutAttempt:
    turn: int
    segment: int
    bonus: int


@dataclass(frozen=True)
class ContinuingEffect:
    """One continuing Mental Power in force on one target."""
    effect_id: str
    kind: str                       # "mind_control" | "mind_scan"
    attacker_id: str
    target_id: str
    order: str | None               # Mind Control's order; None for a scan
    reached: str | None             # a scan's highest level; None for Mind Control
    source_id: str                  # the power that established it
    breakout_modifier: int
    attempts: tuple[BreakoutAttempt, ...] = field(default_factory=tuple)


def _now(session: "CombatSession") -> int:
    tl = session.timeline
    return (int(tl.turn) - 1) * _SEGMENTS_PER_TURN + int(tl.segment)


def _scan_switched_off(session: "CombatSession", effect: ContinuingEffect) -> bool:
    """A Mind Scan is a Constant Power: off breaks the lock (6E1 p.263).

    Off is either the scanner going down (a Constant Power does not stay on
    in an unconscious man) or his Multipower's latest reallocation leaving the
    Mind Scan slot out --- "if it's in a Multipower, he cannot switch the
    slots". A framework this fight never reallocated has "no opinion" (see
    `framework.active_slots`), which leaves the slot as the build has it.
    """
    from kirby_combat.enumeration import is_down
    from kirby_combat.framework import active_slots

    scanner = session.combatants.get(effect.attacker_id)
    if scanner is None or is_down(scanner):
        return True
    for view in getattr(scanner, "framework_view", lambda: [])() or []:
        slot_ids = {s.slot_id for s in view.slots}
        if effect.source_id not in slot_ids:
            continue
        active = active_slots(session, scanner.id, view.framework_id)
        if active and effect.source_id not in active:
            return True
    return False


def continuing_effects(session: "CombatSession") -> list[ContinuingEffect]:
    """Every continuing effect still in force in this fight, oldest first."""
    live: dict[str, ContinuingEffect] = {}
    for evt in session.event_log:
        kind = getattr(evt, "kind", None)
        if kind == "ActionResolved":
            p = getattr(evt, "result_payload", None) or {}
            if p.get("kind") in CONTINUING_KINDS and p.get("established"):
                live[evt.id] = ContinuingEffect(
                    effect_id=evt.id, kind=p["kind"],
                    attacker_id=p["attacker_id"], target_id=p["target_id"],
                    order=p.get("order"), reached=p.get("reached"),
                    source_id=p.get("source_id") or "",
                    breakout_modifier=int(p.get("breakout_modifier", 0)),
                )
        elif kind == "BreakoutRolled":
            eff = live.get(evt.effect_id)
            if eff is None:
                continue
            if evt.broke_free:
                del live[evt.effect_id]
            else:
                live[evt.effect_id] = ContinuingEffect(
                    **{**eff.__dict__, "attempts": eff.attempts + (
                        BreakoutAttempt(evt.turn, evt.segment, evt.bonus),)},
                )
    return [e for e in live.values()
            if not (e.kind == "mind_scan" and _scan_switched_off(session, e))]


def effects_on(session: "CombatSession", target_id: str) -> list[ContinuingEffect]:
    return [e for e in continuing_effects(session) if e.target_id == target_id]


def mind_control_orders(session: "CombatSession", target_id: str) -> list[ContinuingEffect]:
    """The Mind Control orders ``target_id`` is OBEYING right now.

    "he doesn't take any Actions under Mind Control until he attempts and
    fails his first Breakout Roll" (6E1 p.258) --- so an order with no
    attempt yet is in force but not yet obeyed, and is left out.
    """
    return [e for e in effects_on(session, target_id)
            if e.kind == "mind_control" and e.attempts]


def mind_scan_locks(session: "CombatSession", observer_id: str) -> frozenset[str]:
    """The minds ``observer_id`` has mental line of sight to through a lock.

    His own locks at EGO+10 or better (6E1 p.266: "Mentalist can use all
    Mental Powers ... on target") --- and, because "a Mind Scan lock-on is a
    two-way circuit. If the character can mentally attack his target, his
    target can mentally attack him" (p.265), every scanner who holds such a
    lock on HIM.
    """
    out: set[str] = set()
    for e in continuing_effects(session):
        if e.kind != "mind_scan" or e.reached not in ("mental_powers", "all_attacks"):
            continue
        if e.attacker_id == observer_id:
            out.add(e.target_id)
        elif e.target_id == observer_id:
            out.add(e.attacker_id)
    return frozenset(out)


def breakout_due(session: "CombatSession", effect: ContinuingEffect) -> int | None:
    """The Time Chart bonus of a Breakout Roll owed now, or None if none is.

    The first is owed on the target's first Phase after the effect landed,
    at +0. Each later one when the clock has passed the next Time Chart step
    counted from the FIRST attempt.
    """
    if not effect.attempts:
        return 0
    first = effect.attempts[0]
    elapsed = _now(session) - ((first.turn - 1) * _SEGMENTS_PER_TURN + first.segment)
    # A step he slept through is not owed later: a man unconscious from the
    # 1-Turn mark to past the 1-Minute mark rolls once, at +2, not at +2 and
    # then at +1.
    best_taken = max(a.bonus for a in effect.attempts)
    owed = None
    for turns, bonus in _TIME_CHART_TURNS:
        if elapsed >= turns * _SEGMENTS_PER_TURN and bonus > best_taken:
            owed = bonus
    return owed


def roll_breakouts(session: "CombatSession", target_id: str, roller) -> "CombatSession":
    """Make every Breakout Roll ``target_id`` is owed, at the top of his Phase.

    Takes no time (6E1 p.151); recorded as `BreakoutRolled`, one per effect.
    """
    from kirby_cost.engine.rolls import characteristic_roll

    from kirby_combat.mental.mind_control import roll_succeeds
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import BreakoutRolled, make_author_engine

    target = session.combatants[target_id]
    for effect in effects_on(session, target_id):
        bonus = breakout_due(session, effect)
        if bonus is None:
            continue
        number = characteristic_roll(target.ego) + effect.breakout_modifier + bonus
        roll = sum(roller.roll_dice(3))
        session = apply_event(session, BreakoutRolled(
            id=str(uuid.uuid4()), session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc), author=make_author_engine(),
            target_id=target_id, effect_id=effect.effect_id,
            roll=roll, target_number=number, bonus=bonus,
            broke_free=roll_succeeds(roll, number),
            turn=int(session.timeline.turn), segment=int(session.timeline.segment),
        ))
    return session


#: What a man ordered to ``withdraw`` may still do: everything that is not
#: an attack on somebody (6E1 p.256, "forced to flee from the combat").
#: Moving TOWARD an enemy (``move``, ``move_strike``) is not fleeing.
WITHDRAW_KINDS = frozenset({
    "dodge", "recover", "reposition", "disengage", "move_to_cover", "hide",
    "escape_attack", "escape_str", "escape_teleport", "climb", "climb_fast",
    "reallocate", "reconfigure_vpp",
})


@dataclass(frozen=True)
class Obedience:
    """What the orders ``target`` is obeying make of his Phase."""
    enemies: list
    allies: list
    withdraw: bool


def obey(session: "CombatSession", actor, enemies: list, allies: list) -> Obedience:
    """Bend the actor's view of the fight to the Mind Control he obeys.

    * ``spare`` --- nobody on the controller's side is an enemy any more.
    * ``turn`` --- his own standing side-mates are his enemies, and he helps
      nobody.
    * ``withdraw`` --- the menu is cut to `WITHDRAW_KINDS` by the caller.

    He still chooses HOW, with his own chooser: "he has to fight as
    effectively as he does when he's under his own control" (6E1 p.258).
    """
    from kirby_combat.roster import Roster
    from kirby_combat.side import Side

    withdraw = False
    for effect in mind_control_orders(session, actor.id):
        controller = session.combatants.get(effect.attacker_id)
        if effect.order == "spare" and controller is not None:
            theirs = Side.of(controller)
            enemies = [e for e in enemies if Side.of(e) != theirs]
        elif effect.order == "turn":
            enemies = Roster(session).allies_of(actor)
            allies = []
        elif effect.order == "withdraw":
            withdraw = True
    return Obedience(enemies=enemies, allies=allies, withdraw=withdraw)
