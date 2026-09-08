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
from kirby_combat.actions.reactive.abort import is_aborting
from kirby_combat.framework import allocation_for
from kirby_combat.holding import held_object
from kirby_combat.loop.chooser import Chooser, PhaseSituation, validate_choice
from kirby_combat.loop.registry import (
    ResolvedAction, UnresolvableAction, resolve_chosen,
)
from kirby_combat.roster import LastSideStanding, Roster, StopCondition, Verdict
from kirby_combat.scene.geometry import distance_3d
from kirby_combat.side import Side

if TYPE_CHECKING:
    from kirby_combat.encounter import Encounter
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate

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
    winner: "Side | None" = None


@dataclass
class EncounterResult:
    """A fight, driven to its end or to a cap."""

    encounter: "Encounter"
    turns: int = 0
    phases: int = 0
    complete: bool = False
    winner: "Side | None" = None
    skipped_kinds: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def distances_from(scene, actor, others) -> dict[str, float] | None:
    """Metres from ``actor`` to each of ``others``, read off the Scene.

    ``enumerate_actions`` gates range-dependent offers on this: an unknown
    distance means "scene-less, no gate", so returning ``None`` is not the
    same as returning an empty dict and the difference is load-bearing. A
    combatant the scene has no position for is simply absent from the map
    rather than at range 0.
    """
    if scene is None:
        return None
    positions = getattr(scene, "combatant_positions", None) or {}
    here = positions.get(actor.id)
    if here is None:
        return None
    out: dict[str, float] = {}
    for other in others:
        there = positions.get(other.id)
        if there is not None:
            out[other.id] = distance_3d(here, there)
    return out


def next_actor_id(session: "CombatSession") -> str | None:
    """The next combatant with an unspent slot in this Segment's order.

    Reads ``Timeline.acting_order`` --- which is why the stale-order repair
    had to land first: an order left over from an earlier Segment would
    carry its ``has_acted`` flags and skip combatants who had only acted
    then. ``apply_event`` now clears the order on ``SegmentAdvanced``.

    Downed combatants are skipped rather than asked (6E1 p.421). A slot for
    someone who has since been knocked out is consumed silently: they had a
    Phase, and they are in no condition to use it.

    AND SO IS SOMEONE WHO HAS GONE. `Roster` already owns the definition
    of having left --- outside the scene's bounds --- and `standing`
    stopped counting such a man from the day `disengage` was built. This
    did not ask, so the loop kept handing Phases to a fighter who was
    already through the door: at the O.K. Corral, Billy Claiborne was
    off the field at y=-11 and was still asked to decide two Segments
    later, running to y=-23. The scoreboard knew; the loop did not.
    """
    roster = Roster(session)
    for slot in session.timeline.acting_order:
        if slot.has_acted:
            continue
        combatant = session.combatants.get(slot.combatant_id)
        if (combatant is None or is_down(combatant)
                or roster.has_left(slot.combatant_id)):
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
    roster = Roster(session)
    enemies = roster.enemies_of(actor)
    _held = held_object(session, actor_id)

    # THE SCENE, PLUMBED THROUGH. `CombatSession.scene` has always existed
    # and the loop simply never read it, so `has_scene` defaulted to False
    # and every scene-dependent offer -- movement, cover, Images, attacking
    # a construct -- was silently absent from every menu. A fight on a map
    # enumerated as though it were in a void.
    scene = session.scene
    menu = enumerate_actions(
        actor, enemies,
        has_scene=scene is not None,
        scene=scene,
        constructs=list(getattr(scene, "constructs", None) or []) or None,
        distances=distances_from(scene, actor, enemies),
        # THE FRAMEWORK GATE, fed from the build and the fight's own log.
        # `slot_allocation` was a parameter the caller had to keep in step
        # with reallocations it was not otherwise tracking; `allocation_for`
        # assembles it from `framework_view()` (the reserve and slot costs)
        # and the log (which slots this fight switched on).
        slot_allocation=allocation_for(session, actor),
        # ONE ABORT A PHASE. `mark_aborting` refuses a second and raises,
        # which escapes `on_unresolvable="skip"` and kills the fight --- it
        # killed the O.K. Corral benchmark the first time a man dodged
        # twice. Computed here because enumeration holds no session, the
        # same way `slot_allocation` above is assembled by this caller.
        already_aborted=is_aborting(session, actor_id),
        # WHAT HE IS CARRYING. `throw_object` is offered only when these
        # two are supplied, and nothing supplied them --- so a fighter
        # picked a wagon up and the next Phase's menu had no idea, offered
        # the pickup again, and he lifted the same wagon eleven times.
        # Folded from the log here for the same reason `slot_allocation`
        # is: it lives in the fight, not in the caller.
        actor_holding=_held is not None,
        held_construct_id=_held,
    )
    if not menu:
        _mark_acted(session, actor_id)
        return PhaseResult(
            session=session, actor_id=actor_id,
            notes=[f"{actor_id} had no legal action"],
        )

    situation = PhaseSituation(
        actor=actor, menu=menu, enemies=enemies,
        allies=roster.allies_of(actor),
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
    stalemate_after: int = 40,
    on_unresolvable: str = "raise",
    expected_sides=None,
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

    Sides are validated before the first Phase. Two labels differing only
    in case or spacing raise ``AmbiguousSides`` --- a typo that adds an
    army changes who wins, and is otherwise invisible. Pass
    ``expected_sides`` to also reject a side that was never declared,
    which is the only thing that catches a real misspelling.
    """
    Roster(encounter.sessions[0]).validate(expected=expected_sides)

    stop: StopCondition = until or LastSideStanding()
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

    verdict = Roster(encounter.sessions[0]).decide(stop)
    if verdict:
        return EncounterResult(
            encounter=encounter, complete=True, winner=verdict.winner,
            notes=["fight was already decided before the first Phase"],
        )

    quiet = 0
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
            # NOTHING HAPPENING TO ANYBODY. `max_turns` guards LENGTH and
            # was the only guard there was, so a fight that had stopped
            # progressing still ran to the end of it --- the O.K. Corral
            # did 289 Phases of silence three separate ways in one
            # afternoon. Progress is damage, movement, a status landing or
            # a Presence effect; it is NOT "an action resolved", because
            # Setting your aim for the two hundredth time resolves
            # perfectly well.
            if _something_happened(session, phase.session):
                quiet = 0
            else:
                quiet += 1
            encounter = replace(encounter, sessions=[phase.session])
            if quiet >= stalemate_after:
                return EncounterResult(
                    encounter=encounter, turns=turns, phases=phases,
                    complete=False, winner=None, skipped_kinds=skipped,
                    notes=[f"stalemate: nothing happened to anybody for "
                           f"{quiet} Phases"],
                )

            verdict = Roster(phase.session).decide(stop)
            if verdict:
                return EncounterResult(
                    encounter=encounter, turns=turns, phases=phases,
                    complete=True, winner=verdict.winner, skipped_kinds=skipped,
                )

        encounter = encounter.advance_segment(campaign=campaign)
        if encounter.turn != start_turn:
            turns += 1

    return EncounterResult(
        encounter=encounter, turns=turns, phases=phases,
        complete=False, winner=None, skipped_kinds=skipped,
        notes=[f"stopped at the {max_turns}-Turn guard without a decision"],
    )


#: Events that mean something happened TO SOMEBODY. Deliberately not
#: `ActionResolved` on its own: aiming, holding and shuffling a Multipower
#: all resolve cleanly and change nothing anybody would notice.
_PROGRESS_EVENTS = frozenset({
    "MovementResolved", "StatusChanged", "StatusEffectsChanged",
    "PresenceApplied", "EntangleApplied", "FlashApplied",
    "AdjustmentApplied", "ConstructDamaged", "RecoveryTaken",
})


def _something_happened(before: "CombatSession", after: "CombatSession") -> bool:
    """Did this Phase move the fight at all?

    Reads the events the Phase ADDED rather than comparing state, because
    a Phase that hurt somebody and healed them back still happened.
    """
    for event in after.event_log[len(before.event_log):]:
        kind = getattr(event, "kind", "")
        if kind in _PROGRESS_EVENTS:
            return True
        if kind == "ActionResolved":
            payload = getattr(event, "result_payload", None) or {}
            if (float(payload.get("body_dealt", 0) or 0) > 0
                    or float(payload.get("stun_dealt", 0) or 0) > 0):
                return True
    return False
