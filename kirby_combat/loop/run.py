"""The turn loop — whose Phase it is, what they chose, and when it is over.

PeterB, 2026-09-06: *"the -api should not own the turn loop. it just should
extrude it for a networked session"* and *"just all the rules, with a
grounded local-based heart."*

The loop is rules. Which combatants have a Phase in a Segment (6E2 p.18),
who among them acts first (6E2 p.19-21), when the Turn wraps and the free
Post-Segment 12 Recovery fires (6E2 p.131), and when a combatant is out of
the fight (6E1 p.421) are all book rules, and until now every one of them
lived in a web service's driver --- 258 lines of DB-bound "whose Phase is
it" and 38 more of SQL-backed "is it over".

WHAT EACH FUNCTION RETURNS IS THE NETWORK CONTRACT. Every one returns new
state plus the events that produced it. A networked consumer persists and
broadcasts those events; it decides nothing. That is the whole of what
"extrude it for a networked session" asks for, and it is why none of these
functions take a database, a socket, or a callback.

THE LOOP DOES NOT DECIDE ANYTHING. It asks a ``Chooser`` (see
``loop/chooser.py``), validates the answer against the menu it offered, and
resolves it through the registry. A chooser that consults a model lives
outside this engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Callable

from kirby_combat.encounter import SEGMENTS_PER_TURN
from kirby_combat.enumeration import enumerate_actions, is_down
from kirby_combat.loop.chooser import Chooser, PhaseSituation, validate_choice
from kirby_combat.loop.registry import (
    ResolvedAction, UnresolvableAction, resolve_chosen,
)
from kirby_combat.loop.sides import last_side_standing, side_of

if TYPE_CHECKING:
    from kirby_combat.encounter import Encounter
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate

#: A caller-supplied stop condition: ``(is_over, winner)``.
StopCondition = Callable[["CombatSession"], "tuple[bool, str | None]"]


@dataclass
class PhaseResult:
    """One combatant's Phase."""

    session: "CombatSession"
    actor_id: str | None = None
    action_id: str | None = None
    kind: str | None = None
    result: Any = None
    events: list[Any] = field(default_factory=list)
    #: Set when the chosen kind has no resolver and ``on_unresolvable="skip"``.
    skipped_kind: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def acted(self) -> bool:
        return self.action_id is not None and self.skipped_kind is None


@dataclass
class TurnResult:
    """One full Turn: Segments 1..12, then the wrap."""

    encounter: "Encounter"
    phases: list[PhaseResult] = field(default_factory=list)
    complete: bool = False
    winner: str | None = None


@dataclass
class EncounterResult:
    """A fight, driven to its end or to a cap."""

    encounter: "Encounter"
    turns: int = 0
    phases: int = 0
    complete: bool = False
    winner: str | None = None
    skipped_kinds: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _living_enemies(session: "CombatSession", actor) -> list[Any]:
    """Everyone still up who is not on the actor's side.

    Uses ``side_of``, so an unlabelled roster is a free-for-all rather than
    one team with no opponents --- see ``loop/sides.py``.
    """
    mine = side_of(actor)
    return [
        c for c in session.combatants.values()
        if side_of(c) != mine and not is_down(c)
    ]


def _living_allies(session: "CombatSession", actor) -> list[Any]:
    mine = side_of(actor)
    return [
        c for c in session.combatants.values()
        if c.id != actor.id and side_of(c) == mine and not is_down(c)
    ]


def next_actor_id(session: "CombatSession") -> str | None:
    """The next combatant with an unspent slot in this Segment's order.

    Reads ``Timeline.acting_order`` --- which is why the stale-order repair
    had to land first: an order left over from an earlier Segment would
    carry its ``has_acted`` flags and skip combatants who had only acted
    then. ``apply_event`` now clears the order on ``SegmentAdvanced``.

    Downed combatants are skipped rather than asked (6E1 p.421). A slot for
    someone who has since been knocked out is consumed silently: they had a
    Phase, and they are in no condition to use it.
    """
    for slot in session.timeline.acting_order:
        if slot.has_acted:
            continue
        combatant = session.combatants.get(slot.combatant_id)
        if combatant is None or is_down(combatant):
            slot.has_acted = True
            continue
        return slot.combatant_id
    return None


def _mark_acted(session: "CombatSession", combatant_id: str) -> None:
    for slot in session.timeline.acting_order:
        if slot.combatant_id == combatant_id and not slot.has_acted:
            slot.has_acted = True
            return


def run_phase(
    session: "CombatSession",
    chooser: Chooser,
    *,
    template: "CombatTemplate",
    roller,
    on_unresolvable: str = "raise",
) -> PhaseResult:
    """Drive one Phase: enumerate, ask, resolve, mark the slot spent.

    Returns a ``PhaseResult`` whose ``actor_id`` is ``None`` when no one in
    the current acting order has a Phase left --- the loop's signal to
    advance the Segment.

    ``on_unresolvable`` governs a chosen kind the registry cannot execute.
    ``"raise"`` (the default) surfaces ``UnresolvableAction`` naming the
    kind. ``"skip"`` records it on the result and spends the Phase, for a
    caller who wants a long fight to make progress while the registry is
    still filling --- 52 kinds are enumerable and 4 are resolvable today.
    A skip is never silent.
    """
    if on_unresolvable not in ("raise", "skip"):
        raise ValueError(f"on_unresolvable must be 'raise' or 'skip', got {on_unresolvable!r}")

    actor_id = next_actor_id(session)
    if actor_id is None:
        return PhaseResult(session=session, notes=["no unspent slot in this Segment"])

    actor = session.combatants[actor_id]
    enemies = _living_enemies(session, actor)
    menu = enumerate_actions(actor, enemies)
    if not menu:
        _mark_acted(session, actor_id)
        return PhaseResult(
            session=session, actor_id=actor_id,
            notes=[f"{actor_id} had no legal action"],
        )

    situation = PhaseSituation(
        actor=actor, menu=menu, enemies=enemies,
        allies=_living_allies(session, actor),
        session=session,
        segment=session.timeline.segment, turn=session.timeline.turn,
    )
    action = validate_choice(chooser.choose(situation), menu)

    try:
        resolved: ResolvedAction = resolve_chosen(
            session, actor, action, template=template, roller=roller,
        )
    except UnresolvableAction:
        if on_unresolvable == "raise":
            raise
        _mark_acted(session, actor_id)
        return PhaseResult(
            session=session, actor_id=actor_id, action_id=action.action_id,
            kind=action.kind, skipped_kind=action.kind,
            notes=[f"no resolver for {action.kind!r}; Phase spent"],
        )

    _mark_acted(resolved.session, actor_id)
    return PhaseResult(
        session=resolved.session, actor_id=actor_id,
        action_id=action.action_id, kind=action.kind,
        result=resolved.result, events=resolved.events,
    )


def run_encounter(
    encounter: "Encounter",
    chooser: Chooser,
    *,
    roller,
    until: StopCondition | None = None,
    max_turns: int = 20,
    on_unresolvable: str = "raise",
    campaign: Any = None,
) -> EncounterResult:
    """Drive a fight to its end, or to ``max_turns``.

    The default stop condition is ``last_side_standing`` --- over when at
    most one side still has someone up. Any number of sides is legal: two
    teams, a three-way, the battle of four armies, or a free-for-all where
    nobody carries a side label and each fighter is their own. Pass
    ``until`` to replace it (first blood, an objective, a scripted end).

    ``max_turns`` is a guard, not a rule. A fight that reaches it returns
    ``complete=False`` with a note saying so, rather than looping forever
    on a chooser that will not commit.
    """
    stop: StopCondition = until or last_side_standing
    skipped: dict[str, int] = {}

    # TWO ROLLER CONTRACTS, RECONCILED HERE. `roller` is a dice object
    # (`roller.roll_dice(n) -> list[int]`), which is what every resolver
    # wants. `resolve_acting_order` instead takes a ZERO-ARGUMENT callable
    # and sums whatever it returns, because 6E2 p.21's tie-break is a
    # contested DEX Roll -- 3d6 against a target derived from DEX. Passing
    # the dice object straight through raises `'RandomRoller' object is not
    # callable` from inside the tie-break, which reads like a bad argument
    # and is really this mismatch. The loop adapts rather than making every
    # caller know about it.
    def tie_roller() -> list[int]:
        return roller.roll_dice(3)

    phases = 0
    turns = 0

    session = encounter.sessions[0]
    over, winner = stop(session)
    if over:
        return EncounterResult(
            encounter=encounter, complete=True, winner=winner,
            notes=["fight was already decided before the first Phase"],
        )

    while turns < max_turns:
        start_turn = encounter.turn

        # Resolve this Segment's acting order, then spend every slot in it.
        encounter = encounter.run_segment(campaign=campaign, roller=tie_roller)
        while True:
            session = encounter.sessions[0]
            phase = run_phase(
                session, chooser,
                template=encounter._resolve_template(campaign),
                roller=roller, on_unresolvable=on_unresolvable,
            )
            if phase.actor_id is None:
                break
            if phase.skipped_kind:
                skipped[phase.skipped_kind] = skipped.get(phase.skipped_kind, 0) + 1
            phases += 1
            encounter = replace(encounter, sessions=[phase.session])

            over, winner = stop(phase.session)
            if over:
                return EncounterResult(
                    encounter=encounter, turns=turns, phases=phases,
                    complete=True, winner=winner, skipped_kinds=skipped,
                )

        encounter = encounter.advance_segment(campaign=campaign)
        if encounter.turn != start_turn:
            turns += 1

    return EncounterResult(
        encounter=encounter, turns=turns, phases=phases,
        complete=False, winner=None, skipped_kinds=skipped,
        notes=[f"stopped at the {max_turns}-Turn guard without a decision"],
    )
