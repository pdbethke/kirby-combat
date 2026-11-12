"""Test helpers for Multipower splits.

Every Multipower opens a fight with a split its seat STATES (6E1 p.404-406;
spec §5.2, decision 7): `run_phase` poses the opening before Segment 12 and
no combatant ever gets a split chosen for him. A test that is about
something else, and whose fighters happen to carry a Multipower, states the
split here instead --- in the test, where a reader can see it --- rather than
leaving the harness to pick one.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from kirby_combat.framework import validate_split
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import SlotsAllocated, make_author_combatant


def open_with(session: CombatSession, combatant_id: str, framework_id: str,
              points: dict[str, int]) -> CombatSession:
    """``session`` with ``combatant_id``'s Multipower ``framework_id`` opened
    at ``points`` (slot id -> points; a slot not named is off).

    Held to the same rule as an answered opening (`validate_split` against
    the PRICED view, 6E1 p.404-406), and recorded as the same event
    (`SlotsAllocated(opening=True)`), naming every slot as the event
    requires.
    """
    actor = session.combatants[combatant_id]
    view = actor.priced_framework(framework_id)
    if view is None:
        raise KeyError(f"{combatant_id!r} has no framework {framework_id!r}")
    validate_split(view, dict(points))
    full = {s.slot_id: int(points.get(s.slot_id, 0)) for s in view.slots}
    return apply_event(session, SlotsAllocated(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(combatant_id),
        combatant_id=combatant_id, framework_id=framework_id,
        slot_points=full, opening=True,
    ))


def open_on(session: CombatSession, combatant_id: str, slot_name: str) -> CombatSession:
    """``session`` with the Multipower holding the slot named ``slot_name``
    opened with that slot alone, at its full Active Points (`open_with`).

    By NAME, for corpus characters, whose ids a reader cannot check
    against the sheet; the test still states which slot is on.
    """
    actor = session.combatants[combatant_id]
    for view in actor.framework_view():
        if view.kind != "multipower":
            continue
        for slot in view.slots:
            if slot.name.strip() == slot_name:
                return open_with(session, combatant_id, view.framework_id,
                                 {slot.slot_id: int(slot.active_points)})
    raise KeyError(f"{combatant_id!r} has no Multipower slot named {slot_name!r}")


class Opens:
    """Wraps a test's seat so it states the opening split of each
    Multipower it is asked about: ``splits`` maps a combatant id to the
    name of the slot he opens with, alone, at its full Active Points. Every other
    question goes to ``seat``. For a Multipower that appears MID-fight (a
    change into costume, 6E1 p.388), which `open_on` cannot reach before
    the fight starts. An opening it was not told about raises: it never
    picks one.
    """

    def __init__(self, seat, splits: dict[str, str]) -> None:
        self.seat = seat
        self.splits = splits

    def choose(self, situation):
        if not situation.opening:
            return self.seat.choose(situation)
        (offer,) = situation.menu
        actor_id = str(situation.actor.id)
        if actor_id not in self.splits:
            raise KeyError(f"no opening split stated for {actor_id!r}")
        name = self.splits[actor_id]
        (slot,) = [t for t in offer.choice.slots if t.name.strip() == name]
        return offer.action_id + offer.choice.answer({slot.slot_id: slot.max_points})

    def __getattr__(self, name):
        return getattr(self.seat, name)
