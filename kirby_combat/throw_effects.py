"""What a Throw does to a man besides the damage (6E2 p.84-85).

Three things the Throw resolver (`loop/resolvers._throw_grabbed`) left
unbuilt, each from the book:

1. THE THROWER ACTS FIRST. 6E2 p.84: "if the Thrower and Thrown character
   both have their next Phases in the same Segment, the Thrower
   automatically gets to act first, regardless of relative DEX (the
   Thrower's opponent is delayed until after the Throwing character's
   DEX). This applies even if the character makes a Breakfall roll ...
   and/or an Acrobatics roll to keep his feet, but at the GM's option does
   not apply if the target's Breakfall roll succeeds by half." The GM's
   option is not taken (RULING): the rule as written applies.

   Recorded on the Throw's own row (``thrower_first``: the Segment both
   men's next Phases fall in, or None), and folded back by
   `thrower_first_in` when that Segment's order is resolved
   (`Encounter.run_segment`). No event of its own: the row is the record
   of the Throw, and the Segment is a fact about it.

2. KEEPING HIS FEET. 6E2 p.85: "A character may attempt to resist being
   Thrown if he has the Acrobatics Skill. He can keep his feet (or land on
   them) if he succeeds with an Acrobatics roll at -3. However, this
   doesn't prevent him from taking damage from the Throw."

3. THE FALL'S OWN STUN CHECK. A Thrown man who leaves an edge falls
   (`impact.fall`), and that damage is an instance of its own, checked
   against CON on its own (6E2 p.105). The Throw's row was already written
   when he fell, so the landing gets a row of its own (`record_landing`)
   that names him and says whether it Stunned him --- the row
   `statuses._is_stunned` folds.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

#: 6E2 p.85: "an Acrobatics roll at -3".
KEEP_FEET_PENALTY = -3

#: The Throw row key carrying the shared Segment, ``[turn, segment]``.
THROWER_FIRST = "thrower_first"

#: The kind of the row a landing after a Throw writes.
LANDING = "landing"


def _next_phase_of(session: "CombatSession", combatant_id: str, *,
                   acting_now: bool) -> tuple[int, int]:
    """His next Phase from where the fight stands. A man who still has an
    unspent slot in this Segment's order has his next Phase NOW."""
    from kirby_combat.session.timeline import next_phase
    from kirby_combat.tables import segments_for_spd

    timeline = session.timeline
    if not acting_now and any(
            slot.combatant_id == combatant_id and not slot.has_acted
            and slot.segment == timeline.segment
            for slot in timeline.acting_order):
        return (timeline.turn, timeline.segment)
    phases = segments_for_spd(session.combatants[combatant_id].combat_stats().spd)
    return next_phase(phases, timeline.turn, timeline.segment, inclusive=False)


def shared_next_phase(session: "CombatSession", thrower_id: str,
                      thrown_id: str) -> list[int] | None:
    """The Segment both men's next Phases fall in, or None (6E2 p.84)."""
    mine = _next_phase_of(session, thrower_id, acting_now=True)
    his = _next_phase_of(session, thrown_id, acting_now=False)
    return [mine[0], mine[1]] if mine == his else None


def thrower_first_in(session: "CombatSession", turn: int,
                     segment: int) -> dict[str, str]:
    """``{thrower_id: thrown_id}`` for every Throw that gives its Thrower
    the first action in (turn, segment). Folded from the Throw rows."""
    out: dict[str, str] = {}
    for event in session.event_log:
        if getattr(event, "kind", "") != "ActionResolved":
            continue
        payload = getattr(event, "result_payload", None) or {}
        if payload.get("kind") != "throw" or not payload.get("hit"):
            continue
        when = payload.get(THROWER_FIRST)
        if when is not None and (int(when[0]), int(when[1])) == (turn, segment):
            out[str(payload["attacker_id"])] = str(payload["target_id"])
    return out


def keep_feet_roll(session: "CombatSession", thrown_id: str, *, roller) -> dict | None:
    """His Acrobatics roll at -3 to keep his feet, or None without the Skill
    or the wits to use it (`impact.can_save`'s bar, which every save in
    `impact` uses)."""
    from kirby_combat.impact import ACROBATICS, can_save, skill_roll

    if not can_save(session, thrown_id):
        return None
    return skill_roll(session, thrown_id, ACROBATICS, modifier=KEEP_FEET_PENALTY,
                      roller=roller)


def record_landing(session: "CombatSession", *, thrower_id: str, thrown_id: str,
                   landed: dict[str, Any], declaration_event_id: str) -> "CombatSession":
    """The row for a Thrown man's fall: what it did, and whether it Stunned
    him on its own (6E2 p.105)."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ActionResolved, make_author_engine

    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        declaration_event_id=declaration_event_id,
        result_payload={
            "kind": LANDING, "cause": "thrown", "attacker_id": thrower_id,
            "target_id": thrown_id, "fall": landed,
            "status_changes": ["Stunned"] if landed.get("stunned") else [],
        },
    ))
