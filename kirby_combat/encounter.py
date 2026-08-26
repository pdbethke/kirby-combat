"""Encounter -- precise time for one Scene.

6E2 p.8, "COMBAT AND NONCOMBAT TIME": "Unless it looks like there's going
to be a fight (or some other sequence you need to detail precisely, like
a car chase), you don't have to be exact about things like time or
distance." An Encounter is that precisely-timed sequence -- it exists
only while a scene needs Segment-level accounting, and it need not
contain a fight at all: a rocket countdown with zero CombatSessions is a
legitimate Encounter.

Combat begins on Segment 12 (6E2 p.20, "BEGINNING COMBAT"), which is why
``segment`` defaults to 12. A Turn is 12 Segments (6E2 p.18, "SEGMENT"),
so advancing past Segment 12 wraps to Segment 1 of the next Turn.

Deliberately NOT implemented here: Post-Segment 12 Recovery (6E2 p.131
gives every character, even Stunned ones, a free Recovery after Segment
12). Applying that Recovery needs the participants in play and belongs
with the acting-order work, not with this clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate

#: 6E2 p.18, "SEGMENT": a Turn consists of 12 Segments.
SEGMENTS_PER_TURN = 12


@dataclass
class Encounter:
    """Precise time for one Scene, existing only while a sequence needs it.

    Immutable-by-convention like ``Scene``: ``advance_segment`` returns a
    NEW ``Encounter`` via ``dataclasses.replace`` rather than mutating in
    place (``Scene.place_combatant`` sets this precedent).
    """

    id: str
    turn: int = 1
    segment: int = 12  # 6E2 p.20: combat begins on Segment 12.
    current_slot_index: int = 0
    sessions: list["CombatSession"] = field(default_factory=list)
    template: "CombatTemplate | None" = None

    def advance_segment(self) -> "Encounter":
        """Return a new Encounter one Segment later.

        6E2 p.18: a Turn is 12 Segments, so advancing past Segment 12
        wraps to Segment 1 of the next Turn.
        """
        if self.segment >= SEGMENTS_PER_TURN:
            return replace(self, turn=self.turn + 1, segment=1)
        return replace(self, segment=self.segment + 1)
