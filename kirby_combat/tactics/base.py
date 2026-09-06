"""Tactic / Situation / Plan dataclasses + Tactic ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Complication:
    """One complication on a character's sheet (PSYCHOLOGICALLIMITATION,
    ENRAGED, BERSERK, HUNTED, SUSCEPTIBILITY, VULNERABILITY, etc.).

    HD encodes the activation conditions and severity in OPTION /
    ALIAS / NAME free-text — we keep the raw fields here and let
    individual tactics inspect them. ``trigger_keywords`` is a
    convenience: lowercased tokens extracted from name/alias for
    keyword matching ("rage", "fire", "code of honor", etc.)."""
    xmlid: str
    name: str
    alias: str = ""
    notes: str = ""
    levels: int = 0
    trigger_keywords: tuple[str, ...] = ()
    #: Adder OPTIONIDs keyed by adder xmlid, e.g.
    #: {"CIRCUMSTANCES": "UNCOMMON", "CHANCETOGO": "11-",
    #:  "CHANCETORECOVER": "14-"}. HERO stores the go/recover rolls for
    #: ENRAGED/BERSERK here, so this is where rage reads them from.
    adders: dict[str, str] = field(default_factory=dict)


@dataclass
class Situation:
    """Snapshot of what one combatant sees at the moment of decision.

    Used by ``Tactic.applicable()`` and ``Tactic.execute()``. Pure
    data — no engine-side mutation here.
    """
    actor: Any                    # The combatant whose turn it is
    allies: list[Any]             # Combatants on actor's team (may be empty)
    enemies: list[Any]            # Living enemies the actor knows about
    scene_features: list[Any] = field(default_factory=list)  # CoverFeature etc.
    current_segment: int = 0
    turn: int = 1
    # Optional pre-computed lookups so individual tactics don't have to
    # re-scan the DB. Caller fills these.
    actor_complications: list[Complication] = field(default_factory=list)
    actor_skills: dict[str, int] = field(default_factory=dict)  # xmlid → roll value
    enemy_complications: dict[str, list[Complication]] = field(default_factory=dict)


@dataclass
class PlanStep:
    """One phase of a multi-phase tactic.

    The ``kind`` discriminator drives engine wiring:

      "attack": call resolve_attack with attack_view(power_xmlid)
      "presence_attack": PRE attack — emits PRE total, target processes
      "move":   reposition without attacking
      "set":    Set/Aim, +1 OCV next phase
      "wait":   skip phase deliberately (sets up a held action)
      "taunt":  PRE-attack-style social provocation
      "withdraw": full-move retreat
    """
    kind: str
    target_id: str | None = None
    power_xmlid: str | None = None
    notes: str = ""
    # Free-form params for kind-specific data (e.g., taunt text,
    # destination position, held-action trigger).
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    """A tactic's emitted multi-phase plan."""
    tactic_name: str
    rationale: str            # Human-readable why
    steps: list[PlanStep]
    expected_outcome: str = ""


class Tactic(ABC):
    """Base class for named tactics.

    Subclasses must:
      * Set ``name`` (str) — registry key
      * Implement ``applicable(situation) -> bool``
      * Implement ``execute(situation) -> Plan``

    Optional:
      * Override ``priority`` (int, default 0) — orders the applicable
        tactics, and is what a deterministic chooser falls back on when no
        other selector is available. Higher = preferred.
      * Override ``narrative_summary`` for the tactic listing a chooser sees.
    """
    name: str = ""
    priority: int = 0
    narrative_summary: str = ""  # one-liner shown to whatever picks one

    @abstractmethod
    def applicable(self, situation: Situation) -> bool:
        """Return True if this tactic could apply in this situation."""

    @abstractmethod
    def execute(self, situation: Situation) -> Plan:
        """Produce the multi-phase Plan. Caller must check
        ``applicable()`` first."""


@dataclass(frozen=True)
class Basis:
    """Where a tactic comes from -- the rulebook, or someone's judgement.

    An engine that ships heuristics alongside rules owes the reader the
    difference. Of the twenty tactics moved here, three carried a citation.

    ``mechanism`` cites where the book DEFINES the move; ``doctrine`` cites
    where the book advises WHEN to use it. Most tactics have the first and not
    the second: Block is defined at 6E2 p57, and nothing in the book says to
    abort to it when a big hit is incoming -- that part is judgement.

    A citation must be VERIFIED, never derived. The codex stores PDF pages;
    6E2's printed page is two lower (confirmed four times against the book's
    own cross-references) and 6E1 is not calibrated at all. A page number that
    was never checked looks grounded and is worse than none, because it
    borrows the engine's credibility for a guess.
    """
    mechanism: str | None = None      # where the book DEFINES it, e.g. "6E2 p57"
    doctrine: str | None = None       # where the book ADVISES it, e.g. "6E2 p39"
    judgement: str = ""               # why it is sound when the book is silent

    @property
    def is_raw(self) -> bool:
        """True when the book ADVISES this, not merely permits it."""
        return self.doctrine is not None
