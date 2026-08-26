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
from typing import TYPE_CHECKING, Callable, Iterable

from kirby_combat.session.timeline import build_acting_order_for_segment
from kirby_combat.template import DEFAULT_TEMPLATE

if TYPE_CHECKING:
    from kirby_combat.campaign import Campaign
    from kirby_combat.models import StatBlockCombatant
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.session.timeline import ActingSlot
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

    def acting_order(
        self,
        combatants: Iterable["StatBlockCombatant"],
        *,
        campaign: "Campaign | None" = None,
        roller: Callable[[], int] | None = None,
    ) -> list["ActingSlot"]:
        """Build the acting order for ``self.segment``, honoring the
        resolved CombatTemplate's ``tie_rule`` (6E2 p.21).

        This is the wiring `CombatTemplate.tie_rule` never had: it plumbs
        the resolved template's tie-breaking rule into
        `build_acting_order_for_segment`, which otherwise falls back to
        its own `TieRule.INT_THEN_PRE` default.

        Template resolution: when ``campaign`` is given, the template is
        resolved via `campaign.resolve_template` (encounter-level
        override, else the campaign's default -- see that function's
        docstring). When no ``campaign`` is given, ``self.template`` is
        used if set, else the module-level `DEFAULT_TEMPLATE`
        (`TieRule.DEX_ROLL`, 6E2 p.21's default rule). This fallback lets
        an Encounter resolve acting order standalone -- a fight can exist
        before the Campaign/World hierarchy above it is populated, and
        requiring a Campaign here would make Encounter unusable on its
        own.

        `TieRule.DEX_ROLL` (6E2 p.21's default: a contested DEX Roll)
        requires a ``roller`` -- `build_acting_order_for_segment` raises
        `ValueError` if the resolved tie_rule needs one and none is
        supplied. Callers whose template resolves to `DEX_ROLL` (which
        includes the engine-wide default template) must pass a roller;
        this method does not silently substitute a rule that needs none.
        """
        if campaign is not None:
            from kirby_combat.campaign import resolve_template

            template = resolve_template(campaign, self)
        else:
            template = self.template or DEFAULT_TEMPLATE

        return build_acting_order_for_segment(
            combatants, self.segment, tie_rule=template.tie_rule, roller=roller,
        )
