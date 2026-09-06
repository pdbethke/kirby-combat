"""Brief — one Phase, written down.

WHAT THIS IS FOR. A chooser that reads text needs the Phase described:
who is acting, what shape they are in, who is standing where, and what
they may legally do. That description was the last thing keeping a fight
inside the parked kirby-api wrapper, where the equivalent builder is
160-odd lines that --- measured 2026-09-06 --- touch the database **zero**
times. It was already a pure function of engine state; only its location
was wrong.

WHY THIS IS NOT A VIOLATION OF THE ENGINE'S BOUNDARIES, which is worth
saying because two other homes were considered and rejected:

* The engine already renders itself to text and always has ---
  ``LegalAction.summary`` is a readable label, ``Tactic.narrative_summary``
  is "the one-liner shown to whatever picks one". A Brief is those, gathered
  into a page. It describes combat state and knows nothing about what reads
  it.
* ``kirby-ai`` was the obvious candidate and is the wrong one by its own
  charter, which says it owns the network hop and the policy around it ---
  and explicitly not content, rules, or rows. A description of a Phase is
  content, not transport.
* A module of its own would be one class with no second occupant.

**No word here names anything that reads a Brief**, and
``tests/test_vocabulary.py`` enforces that. The engine writes the page; who
reads it is somebody else's business. That is the same seam as ``Chooser``
--- the engine asks, and never learns what answered.

STABLE AND PARSEABLE, NOT PRETTY. Each action is listed with its
``action_id`` in brackets, because that token is what a chooser returns and
what ``validate_choice`` checks. The rest is a state line per combatant.
Formatting choices here are a view, not a rule --- a caller who wants a
different page builds one from the same objects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kirby_combat.enumeration import is_down
from kirby_combat.roles import classify_role
from kirby_combat.side import Side

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.loop.chooser import PhaseSituation


def _stat(combatant, name: str, default: int = 0) -> int:
    stats = combatant.combat_stats()
    return int(getattr(stats, name, default) or default)


@dataclass(frozen=True)
class CombatantLine:
    """One combatant as a reader sees them.

    Enemy stats are shown as freely as the actor's. That is DELIBERATE and
    worth naming: the anti-metagaming line in this system is drawn by
    PERCEPTION --- an actor cannot target what it cannot perceive --- not by
    hiding numbers from whoever is choosing. Showing STUN and DCV but
    withholding, say, power names would be inconsistent rather than
    principled.
    """

    combatant: object

    @property
    def name(self) -> str:
        return getattr(self.combatant, "name", None) or self.combatant.id

    @property
    def side(self) -> Side:
        return Side.of(self.combatant)

    @property
    def is_down(self) -> bool:
        return is_down(self.combatant)

    @property
    def role(self) -> str:
        return classify_role(self.combatant)

    def render(self) -> str:
        state = self.combatant.state
        bits = [
            f"STUN {state.current_stun}/{_stat(self.combatant, 'max_stun')}",
            f"BODY {state.current_body}/{_stat(self.combatant, 'max_body')}",
            f"END {state.current_end}/{_stat(self.combatant, 'max_end')}",
            f"OCV {_stat(self.combatant, 'ocv')}",
            f"DCV {_stat(self.combatant, 'dcv')}",
        ]
        line = f"{self.name} [{self.side}] {', '.join(bits)}, role={self.role}"
        return f"{line} -- DOWN" if self.is_down else line

    def __str__(self) -> str:
        return self.render()


class Brief:
    """A written description of one Phase.

    Built from the engine's own ``PhaseSituation``, so it carries exactly
    what the actor was offered --- no more, and nothing re-derived.
    """

    def __init__(self, situation: "PhaseSituation") -> None:
        self._situation = situation

    @property
    def actor(self) -> CombatantLine:
        return CombatantLine(self._situation.actor)

    @property
    def allies(self) -> list[CombatantLine]:
        return [CombatantLine(c) for c in self._situation.allies]

    @property
    def enemies(self) -> list[CombatantLine]:
        return [CombatantLine(c) for c in self._situation.enemies]

    @property
    def menu(self) -> list["LegalAction"]:
        return list(self._situation.menu)

    @property
    def action_ids(self) -> list[str]:
        """The tokens a chooser may return. ``validate_choice`` checks
        against exactly this list."""
        return [a.action_id for a in self.menu]

    def render(self) -> str:
        situation = self._situation
        lines = [
            f"Turn {situation.turn}, Segment {situation.segment}.",
            "",
            f"YOU control: {self.actor.render()}",
        ]

        if self.allies:
            lines.append("")
            lines.append("Allies:")
            lines.extend(f"  {line.render()}" for line in self.allies)

        lines.append("")
        lines.append("Enemies:" if self.enemies else "Enemies: none standing.")
        lines.extend(f"  {line.render()}" for line in self.enemies)

        lines.append("")
        lines.append(f"Legal actions this Phase ({len(self.menu)}):")
        # The action_id is bracketed because it is the token a chooser
        # returns; the summary is for the reader, the id is the contract.
        lines.extend(f"  [{a.action_id}] {a.summary}" for a in self.menu)
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.render()

    def __len__(self) -> int:
        """How many actions were offered."""
        return len(self.menu)
