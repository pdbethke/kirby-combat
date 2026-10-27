"""Getting up off the ground (6E2 p.51, 6E1 p.68).

Prone had a source (Trip, a martial Target Falls, and now Knockback, a
Throw and a fall) and no way out: `statuses._is_prone` clears only on a
`StatusEffectsChanged` naming PRONE in `removed`, and nothing in the engine
ever wrote one, so a man knocked down stayed down for the rest of the
fight. This module writes it, two ways:

- STAND UP, an action: "Getting back to one's feet takes a Half Phase
  Action" and costs no END (6E2 p.51).
- BREAKFALL, at the top of his Phase: "a character can use Breakfall to
  stand up from falling, being prone, lying down, or otherwise being on the
  ground without taking a Half Phase. If the roll succeeds, the character
  gets to his feet as a Zero Phase Action" (6E1 p.68) -- and then has his
  whole Phase. RULING: anybody who owns the Skill makes the attempt when
  his Phase begins; a man would always rather be up.

A Half Phase Action since the Phase can be spent in halves
(`kirby_combat/action_time.py`): he stands, and the same Phase comes back to
him for an attack or another Half Phase Action. A man on the ground can also
fight from there, at 6E2 p.129's -2 OCV and half DCV
(`cv_modifiers._ground_cv_modifiers`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from kirby_combat.statuses import PRONE, statuses_for


def is_prone(session, combatant_id: str) -> bool:
    return PRONE in statuses_for(session, combatant_id)


def _on_his_feet(session, combatant_id: str):
    """The one row that clears Prone (see `statuses._is_prone`)."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import StatusEffectsChanged, make_author_combatant

    return apply_event(session, StatusEffectsChanged(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(combatant_id),
        combatant_id=combatant_id, added=frozenset(), removed=frozenset({PRONE}),
    ))


def stand_up(session, combatant_id: str):
    """He gets to his feet (6E2 p.51). Returns the session and the payload
    for the action's row. Raises if he is not down: the offer is made only
    to a prone man, and standing a standing man up is a caller bug."""
    if not is_prone(session, combatant_id):
        raise ValueError(f"{combatant_id!r} is not prone; there is nothing to stand up from")
    return _on_his_feet(session, combatant_id), {
        "kind": "stand_up", "combatant_id": combatant_id,
        "phase": "half", "end_spent": 0,
    }


def breakfall_to_feet(session, combatant_id: str, roller):
    """6E1 p.68's Zero Phase stand-up, tried at the top of a prone man's Phase.

    Rolls only for a man who is prone, owns BREAKFALL and is in a state to
    roll (`impact.can_save`). Writes the attempt either way -- a declaration
    and a resolution carrying the roll -- and, on a success, the row that
    puts him on his feet. Returns the session unchanged when no roll is owed.
    """
    from kirby_combat.impact import BREAKFALL, can_save, skill_roll
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import (
        ActionDeclared,
        ActionResolved,
        make_author_combatant,
    )

    if not is_prone(session, combatant_id) or not can_save(session, combatant_id):
        return session
    save = skill_roll(session, combatant_id, BREAKFALL, modifier=0, roller=roller)
    if save is None:
        return session
    now = datetime.now(timezone.utc)
    declared = ActionDeclared(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=now,
        author=make_author_combatant(combatant_id), combatant_id=combatant_id,
        action_type="stand_up", targets=[], parameters={"breakfall": True},
    )
    s = apply_event(session, declared)
    s = apply_event(s, ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=now, author=make_author_combatant(combatant_id),
        declaration_event_id=declared.id,
        result_payload={"kind": "stand_up", "combatant_id": combatant_id,
                        "phase": "zero", "breakfall": save,
                        "stood": bool(save["made"])},
    ))
    if save["made"]:
        s = _on_his_feet(s, combatant_id)
    return s
