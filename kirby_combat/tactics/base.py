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
    #: Allies who are DOWN --- kept apart from `allies` on purpose.
    #:
    #: TWO DIFFERENT QUESTIONS. `allies` answers "who can help me fight",
    #: and three tactics read it that way: `coordinated_focus_fire`
    #: counts them, `shield_allies` picks the frailest to stand in front
    #: of, `bait_enraged` treats them as alternative targets. Putting a
    #: dying man in that list would have him counted as a partner,
    #: shielded where he lies, and offered as bait.
    #:
    #: `stabilize_the_dying` asks the other question, and `run.py` says
    #: why in its own words: `allies_of` excluding the down "is right for
    #: 'who can help me fight' and exactly wrong for the man on the
    #: ground who needs somebody to kneel beside him."
    fallen_allies: list[Any] = field(default_factory=list)
    #: enemy_id -> metres between the actor and that enemy.
    #:
    #: THE ONE FACT MELEE DEPENDS ON, and this object did not carry it.
    #: `disarm_the_armed` fired zero times because a Disarm is legal only
    #: within reach, the tactic could not ask, and so it named the
    #: biggest gun on the field -- a man usually across the lot, whose
    #: plan `TacticChooser` then discarded. `close_and_strike` plans
    #: [close, strike] because it cannot ask either, and
    #: `grab_and_throw` gates on STR 30 instead of distance.
    #:
    #: EMPTY MEANS UNKNOWN, NOT FAR. A scene-less fight has no positions;
    #: reading that as "out of reach" would silently disable every melee
    #: tactic in the catalogue's own suite. See `in_reach`.
    distances_m: dict[str, float] = field(default_factory=dict)
    #: The actor's effective melee reach in metres (6E2 p.56; 1m base).
    reach_m: float = 1.0
    scene_features: list[Any] = field(default_factory=list)  # CoverFeature etc.
    current_segment: int = 0
    turn: int = 1
    # Optional pre-computed lookups so individual tactics don't have to
    # re-scan the DB. Caller fills these.
    actor_complications: list[Complication] = field(default_factory=list)
    actor_skills: dict[str, int] = field(default_factory=dict)  # xmlid → roll value
    enemy_complications: dict[str, list[Complication]] = field(default_factory=dict)
    #: The fight, when the caller has one. Optional because most callers do
    #: not: `threat` falls back to what is visible without it.
    session: Any = None

    def in_reach(self, enemy_id: str) -> bool:
        """Whether `enemy_id` is close enough to touch.

        Asks `kirby_combat.actions.reach.within_reach` --- the same
        predicate enumeration uses --- rather than comparing numbers
        here, so a tactic and the menu cannot disagree about who is
        adjacent. The enumerator carries a comment about exactly that
        class of disagreement.

        True when the distance is unknown: absent positions mean a
        scene-less fight, not a distant enemy, and `_melee_gate` takes
        the same branch for the same reason.
        """
        from kirby_combat.actions.reach import within_reach

        distance = (self.distances_m or {}).get(enemy_id)
        if distance is None:
            return True
        return bool(within_reach(distance, self.reach_m).in_reach)

    def enemies_in_reach(self) -> list[Any]:
        """The enemies this actor could touch this Phase."""
        return [e for e in self.enemies
                if self.in_reach(getattr(e, "id", None))]

    @property
    def threat(self) -> dict[str, float]:
        """`enemy id -> how dangerous that one is`. See `kirby_combat.threat`.

        A property rather than a filled-in field: it is derived from the
        enemies and the log this Situation already carries, and a second
        copy that a caller had to remember to populate would go stale.
        """
        from kirby_combat.threat import threat_map

        return threat_map(self.enemies, session=self.session)


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
