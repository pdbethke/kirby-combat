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

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from kirby_combat.encounter import SEGMENTS_PER_TURN
from kirby_combat.enumeration import enumerate_actions, is_down
from kirby_combat.pre_attacks.presence_effects import PresenceEffects, can_act
from kirby_combat.actions.reactive.abort import is_aborting
from kirby_combat.charges import spent_charges
from kirby_combat.statuses import stunned_or_recovering_for
from kirby_combat.concealment import concealment_for
from kirby_combat.framework import allocation_for
from kirby_combat.holding import held_object
from kirby_combat.loop.chooser import Chooser, PhaseSituation, validate_choice
from kirby_combat.loop.registry import (
    ResolvedAction, UnresolvableAction, resolve_chosen,
)
from kirby_combat.roster import LastSideStanding, Roster, StopCondition, Verdict
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import PhaseSpent, make_author_engine
from kirby_combat.scene.construct import constructs_in
from kirby_combat.scene.geometry import distance_3d
from kirby_combat.side import Side

if TYPE_CHECKING:
    from kirby_combat.encounter import Encounter
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate

@dataclass
class PhaseResult:
    """One combatant's Phase, and the fight it left behind.

    `encounter` rather than a bare session, because a Phase may now be
    the one that ends a Segment: `run_phase` advances the clock itself
    (see its docstring), and an `Encounter` is where the clock lives. The
    `session` a consumer reads is a VIEW of it rather than a second
    field, so the two cannot drift.
    """

    encounter: "Encounter"
    actor_id: str | None = None
    action_id: str | None = None
    kind: str | None = None
    result: Any = None
    #: EVERY event this `run_phase` call appended to the session's log,
    #: in order --- the clock's included. A consumer persists what it is
    #: handed, so a list assembled from the sub-calls (which is what this
    #: was) is a second account of the Phase that can disagree with the
    #: record, and did: the acting order, the Segment advance and the
    #: free Post-Segment 12 Recovery were written to the log and never
    #: handed back, and a consumer replaying what it had persisted hit a
    #: sequence gap on its second step.
    events: list[Any] = field(default_factory=list)
    #: Set when the chosen kind has no resolver and ``on_unresolvable="skip"``.
    skipped_kind: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def session(self) -> "CombatSession":
        """The fight this Phase happened in."""
        return self.encounter.sessions[0]

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


def _skip_reason(session: "CombatSession", combatant_id: str) -> str | None:
    """Why this combatant cannot use the Phase he has --- or None.

    THE ONE READING of "he has a slot and cannot use it". `resolve_next_
    actor` spends the slot and `next_actor_id` merely reports who is next,
    and if each asked the question its own way they would eventually
    answer differently about the same man.

    Downed combatants are skipped rather than asked (6E1 p.421): they had
    a Phase, and they are in no condition to use it.

    AND SO IS SOMEONE WHO HAS GONE. `Roster` already owns the definition
    of having left --- outside the scene's bounds --- and `standing`
    stopped counting such a man from the day `disengage` was built. This
    did not ask, so the loop kept handing Phases to a fighter who was
    already through the door: at the O.K. Corral, Billy Claiborne was
    off the field at y=-11 and was still asked to decide two Segments
    later, running to y=-23. The scoreboard knew; the loop did not.
    """
    combatant = session.combatants.get(combatant_id)
    if combatant is None or is_down(combatant):
        return "down"
    if Roster(session).has_left(combatant_id):
        return "left"
    return None


def resolve_next_actor(
    session: "CombatSession",
) -> tuple["CombatSession", str | None, list[PhaseSpent]]:
    """Whose Phase it is --- spending, IN THE LOG, the slots nobody can use.

    THE SKIP IS A SPEND AND IT WAS INVISIBLE. `next_actor_id` used to flip
    `has_acted` in place for a man who was down or gone, which is the
    right rule and the wrong place: `apply_event` deliberately folds no
    stun or body, so a consumer rebuilding the fight from its log alone
    could not know he was down, did not skip him, and handed the Phase to
    a different man than the fight that ran. Measured: the original
    reached `c`, the replay reached `b`.

    So the skip emits `PhaseSpent(reason="down"|"left")` like any other
    spend, through the same `_mark_acted` door, and rides out on
    `PhaseResult.events` with the rest. A consumer that folds no stats at
    all now lands on the same actor, because the log says who was passed
    over and why.

    Returns the new session (slots spent), the actor, and the events.
    """
    events: list[PhaseSpent] = []
    while True:
        actor_id: str | None = None
        skip: str | None = None
        for slot in session.timeline.acting_order:
            if slot.has_acted:
                continue
            reason = _skip_reason(session, slot.combatant_id)
            if reason is None:
                actor_id = slot.combatant_id
            else:
                actor_id, skip = slot.combatant_id, reason
            break
        if actor_id is None:
            return session, None, events
        if skip is None:
            return session, actor_id, events
        session, event = _mark_acted(session, actor_id, reason=skip)
        events.append(event)


def next_actor_id(session: "CombatSession") -> str | None:
    """The next combatant who can use a slot in this Segment's order.

    A QUESTION, NOT A MOVE. This used to spend the slot of anyone it
    passed over, so asking whose Phase it was changed the fight ---
    invisibly, and off stats a replayed session does not fold.
    `resolve_next_actor` does the spending now, in the log; this reports
    the same answer and writes nothing.

    Reads ``Timeline.acting_order`` --- which is why the stale-order repair
    had to land first: an order left over from an earlier Segment would
    carry its ``has_acted`` flags and skip combatants who had only acted
    then. ``apply_event`` clears the order on ``SegmentAdvanced``.
    """
    for slot in session.timeline.acting_order:
        if slot.has_acted:
            continue
        if _skip_reason(session, slot.combatant_id) is None:
            return slot.combatant_id
    return None


def _mark_acted(
    session: "CombatSession", combatant_id: str, *, reason: str = "acted",
) -> tuple["CombatSession", PhaseSpent]:
    """Spend this combatant's slot --- in the log, not just in memory.

    THE SPEND IS A DECISION AND BELONGS IN THE RECORD. This flipped
    `slot.has_acted` in place and told nobody, so a fight rebuilt from its
    log had every slot unspent and handed the same man the Segment's every
    Phase forever. The flag is now the EFFECT of applying the event (see
    `session/apply.py`), which is what makes the two paths --- the fight
    that ran and the fight replayed from its log --- produce the same
    timeline rather than two that agree by coincidence.

    THE ONE DOOR every spend goes through, whoever is spending and for
    whatever reason --- a Phase used, or one its owner was in no
    condition to use (`reason`, see `PhaseSpent`).

    Returns the new session AND the event, because the event is part of
    this Phase's output: a networked consumer persists and broadcasts what
    a `PhaseResult` hands it, and a spend it never sees is a spend it
    cannot replay.
    """
    event = PhaseSpent(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_engine(),
        combatant_id=combatant_id,
        segment=session.timeline.segment,
        turn=session.timeline.turn,
        reason=reason,
    )
    return apply_event(session, event), event


def _with(encounter: "Encounter", session: "CombatSession") -> "Encounter":
    """The same Encounter carrying this session --- the one place the two
    are put back together, so a Phase cannot return a session the clock
    it came from has not seen."""
    return replace(encounter, sessions=[session])


def _advance_to_an_actor(
    encounter: "Encounter", *, campaign, tie_roller,
) -> tuple["Encounter", str | None]:
    """Find a Segment somebody can act in, advancing the clock to reach it.

    THE ADVANCE, IN ONE PLACE. `run_encounter` held this --- resolve the
    Segment's order, spend every slot in it, `advance_segment`, repeat ---
    so `run_phase` could not finish a fight and any consumer stepping by
    Phase had to copy it. Both now come through here.

    An order is resolved (`Encounter.run_segment`, 6E2 p.18-21) only when
    the session is carrying none: a rehydrated fight mid-Segment already
    has the order its log recorded, and resolving a second one would
    re-roll the tie-break and draw dice the fight that ran never drew.

    Advancing is `Encounter.advance_segment`, which is what fires 6E2
    p.131's free Post-Segment 12 Recovery, p.109's bleeding to death, the
    Adjustment fade and `SegmentAdvanced` --- one door for those too.

    BOUNDED BY A TURN, not by a number somebody picked: 6E2 p.18's Turn
    is twelve Segments and every combatant with a SPD of at least 1 has a
    Phase in one of them, so a whole Turn with nobody able to act means
    nobody can act at all. Returns `actor_id=None` in that case and lets
    the caller say so.

    Everything this writes down --- the `PhaseSpent` for everyone passed
    over, the `ActingOrderResolved` for each Segment resolved, the
    `SegmentAdvanced` and the free Post-Segment 12 `RecoveryTaken` --- is
    in the session's log when it returns, and `run_phase` hands the whole
    tail of that log back. Nothing is collected here to be assembled into
    a second account of the same Phase.
    """
    for _ in range(SEGMENTS_PER_TURN + 1):
        session = encounter.sessions[0]
        if not session.timeline.acting_order:
            encounter = encounter.run_segment(
                campaign=campaign, roller=tie_roller,
            )
            session = encounter.sessions[0]
        session, actor_id, _passed_over = resolve_next_actor(session)
        encounter = _with(encounter, session)
        if actor_id is not None:
            return encounter, actor_id
        encounter = encounter.advance_segment(campaign=campaign)
    return encounter, None


def run_phase(
    encounter: "Encounter",
    chooser: Chooser,
    *,
    roller,
    on_unresolvable: str = "raise",
    campaign: Any = None,
    until: StopCondition | None = None,
) -> PhaseResult:
    """Step the WHOLE fight by one Phase --- the clock included.

    THE ONE STEP DOOR. This used to take a session and stop dead at the
    end of a Segment: once the order was spent it returned
    ``actor_id=None`` for ever, and only ``Encounter.run_segment`` /
    ``advance_segment`` could move on. ``run_encounter`` knew that and
    held the advance logic itself, so a consumer that steps a fight one
    Phase at a time --- which is exactly what a networked consumer does
    --- could not finish one, and the only alternative was a second copy
    of the advance.

    So the advance lives here, in the one place, and ``run_encounter`` is
    a loop over this function plus its guards. When the current Segment's
    order is spent (or none has been resolved yet) this resolves the next
    one, advancing the Segment and the Turn through
    ``Encounter.advance_segment`` --- which is what fires 6E2 p.131's
    free Post-Segment 12 Recovery, p.109's bleeding, the Adjustment fade
    and ``SegmentAdvanced`` --- until it finds a Segment somebody can act
    in.

    THE SIGNATURE, for a consumer: ``run_phase(encounter, chooser, *,
    roller, on_unresolvable="raise", campaign=None, until=None)``. It
    takes the ``Encounter`` because that is where the clock is; the
    template is resolved from the Encounter and the campaign exactly as
    ``advance_segment`` and ``run_segment`` resolve it, rather than being
    passed in beside them where the two could disagree. The result
    carries the new ``Encounter``; ``result.session`` is a view of it.

    ``actor_id`` is ``None`` in exactly ONE case now: the fight is
    already decided by ``until`` (default: last side standing). Nothing
    is emitted in that case. Every other return has an actor.

    ``roller`` serves both contracts. Resolvers want a dice object; 6E2
    p.21's tie-break wants a zero-argument callable, because it is a
    contested DEX Roll. The adaptation is here rather than in every
    caller --- and here rather than in ``run_encounter``, so a fight
    stepped one Phase at a time draws the same dice in the same order as
    one driven by ``run_encounter``.

    ``on_unresolvable`` governs a chosen kind the registry cannot execute.
    ``"raise"`` (the default) surfaces ``UnresolvableAction`` naming the
    kind. ``"skip"`` records it on the result and spends the Phase, for a
    caller who wants a long fight to make progress while the registry is
    still filling --- 52 kinds are enumerable and 4 are resolvable today.
    A skip is never silent.
    """
    if on_unresolvable not in ("raise", "skip"):
        raise ValueError(f"on_unresolvable must be 'raise' or 'skip', got {on_unresolvable!r}")

    stop: StopCondition = until or LastSideStanding()
    template = encounter._resolve_template(campaign)

    # EVERYTHING THIS CALL WRITES DOWN, measured rather than assembled.
    # `PhaseResult.events` used to be built piecewise from the sub-calls
    # -- the skips, the resolver's own events, the spend -- and the
    # clock's events were simply not among them: `run_segment`'s
    # `ActingOrderResolved`, `advance_segment`'s `SegmentAdvanced` and the
    # free Post-Segment 12 `RecoveryTaken` went into the log and were
    # never handed back. Measured by a consumer over eight Phases: four
    # steps lost events outright and one returned three of its nine, so a
    # consumer persisting what it is handed raised `event sequence
    # mismatch: expected 2, got 3` on its second step.
    #
    # A list assembled from the parts is a second statement of "what
    # happened this Phase", and it disagreed with the log. The log is the
    # record; this is the tail of it.
    log_before = len(encounter.sessions[0].event_log)

    # TWO ROLLER CONTRACTS, RECONCILED HERE --- see the docstring. Passing
    # the dice object straight into the tie-break raises `'RandomRoller'
    # object is not callable`, which reads like a bad argument and is
    # really this mismatch.
    def tie_roller() -> list[int]:
        return roller.roll_dice(3)

    # A FIGHT THAT IS OVER EMITS NOTHING FURTHER. Asked before the clock
    # is touched, so a decided fight cannot be advanced a Segment by
    # somebody asking it for one more Phase.
    if Roster(encounter.sessions[0]).decide(stop):
        return PhaseResult(
            encounter=encounter, notes=["the fight is already decided"],
        )

    encounter, actor_id = _advance_to_an_actor(
        encounter, campaign=campaign, tie_roller=tie_roller,
    )
    session = encounter.sessions[0]
    if actor_id is None:
        # `_advance_to_an_actor` exhausts a whole Turn before giving up,
        # and every combatant with a SPD of at least 1 has a Phase
        # somewhere in a Turn -- so this is not "wait for the next
        # Segment", it is "nobody in this fight can ever act again", and
        # the fight is not decided either (that was asked above). Saying
        # so is the only honest answer; returning a quiet `actor_id=None`
        # is what let a consumer spin.
        raise ValueError(
            f"no combatant in session {session.id!r} could act in a whole "
            f"Turn (Segment {session.timeline.segment}, Turn "
            f"{session.timeline.turn}) and the fight is not decided"
        )

    actor = session.combatants[actor_id]

    # HELD BY TERROR. 6E2 p.139 stops the target outright from `awed`
    # upward, and `presence_effects.can_act` has said so all along --- it
    # was called NOWHERE outside its own module, so a man the rules had
    # frozen took his Phase and shot somebody. Only the half-DCV half of
    # the result was wired in (through the CV seam); the "takes no Action"
    # half did nothing at all.
    #
    # He forfeits ONE Full Phase, not the tier's whole duration: `awed` is
    # five minutes and `overwhelmed` an hour, and gating every Phase would
    # delete a combatant from the fight on one good shout. `forfeit_phase`
    # records the spend so the next Phase is his again.
    #
    # Consumed silently, the same way `next_actor_id` consumes the slot of
    # someone unconscious or gone: they had a Phase and were in no
    # condition to use it.
    if not can_act(session, actor_id):
        session = PresenceEffects.forfeit_phase(session, actor_id)
        session, spent = _mark_acted(session, actor_id)
        return PhaseResult(
            encounter=_with(encounter, session), actor_id=actor_id,
            events=session.event_log[log_before:],
            notes=[f"{actor_id} is held by a Presence Attack and forfeits "
                   f"the Phase"],
        )

    roster = Roster(session)
    enemies = roster.enemies_of(actor)
    _held = held_object(session, actor_id)

    # THE SCENE, PLUMBED THROUGH. `CombatSession.scene` has always existed
    # and the loop simply never read it, so `has_scene` defaulted to False
    # and every scene-dependent offer -- movement, cover, Images, attacking
    # a construct -- was silently absent from every menu. A fight on a map
    # enumerated as though it were in a void.
    scene = session.scene
    # Bound once rather than computed inline: the PhaseSituation below
    # hands the SAME measurements to the tactic layer, and measuring
    # twice is how a tactic and the offer it names come to disagree.
    distances = distances_from(scene, actor, enemies)
    # WHO THIS ACTOR IS HOLDING. `held_target_ids` gates the `throw`
    # offer and its own comment says the driver should pre-compute it:
    # "lets the driver pre-compute who's eligible without this function
    # needing DB access." The driver never did, so the parameter was
    # always None and `throw` has never been offered in any fight this
    # engine has run -- the same shape as `allow_coordinate`.
    #
    # `Grab.is_grabbed` was written for exactly this and never called. It
    # returns (held, grabber_id), so the grabber check is what stops a
    # man throwing somebody another man is holding.
    from kirby_combat.actions.grab import Grab

    held_by_actor = frozenset(
        e.id for e in enemies
        if Grab.is_grabbed(session, e.id) == (True, actor_id)
    )
    menu = enumerate_actions(
        actor, enemies,
        has_scene=scene is not None,
        scene=scene,
        # Authored constructs AND the scene's own destructible walls ---
        # see `constructs_in`. The projection existed and nothing called
        # it, so no building in any fight this engine ever ran was a thing
        # you could hit.
        constructs=((constructs_in(scene, session=session) or None)
                    if scene is not None else None),
        distances=distances,
        held_target_ids=held_by_actor or None,
        # AND WHO IS HOLDING HIM. 6E2 p.64 gives a grabbed man an
        # immediate Casual STR roll to break free; the ladder below was
        # keyed to Entangle only, so he had no offer at all.
        grabbed_by=Grab.is_grabbed(session, actor_id)[1],
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
        # MAY HE ABORT AT ALL --- one question, and `mark_aborting`
        # refuses for two reasons. This asked only whether he had already
        # aborted; 6E2 p.106's "a character who's Stunned or recovering
        # from being Stunned ... cannot Abort to a defensive Action" was
        # left to escape as a ValueError past `on_unresolvable="skip"`,
        # which is what it did to a model-driven street fight.
        can_abort=not (
            is_aborting(session, actor_id)
            or stunned_or_recovering_for(session, actor_id)
        ),
        # AMMUNITION. `used_charges` sat on `HeroCombatState` for a long
        # time, documented and serialized both ways, written by nothing
        # and read by nothing, so nobody ever had to reload. Folded from
        # the log here for the same reason everything else is.
        spent_charges=spent_charges(session, actor_id),
        # WHAT HE IS CARRYING. `throw_object` is offered only when these
        # two are supplied, and nothing supplied them --- so a fighter
        # picked a wagon up and the next Phase's menu had no idea, offered
        # the pickup again, and he lifted the same wagon eleven times.
        # Folded from the log here for the same reason `slot_allocation`
        # is: it lives in the fight, not in the caller.
        actor_holding=_held is not None,
        held_construct_id=_held,
        # WHO HE CANNOT SEE. `enumerate_actions` has always taken this map
        # and this caller never passed one, so the perception gate ran
        # blind to hiding: a man who had just vanished stayed on
        # everybody's list of things to shoot, and the Phase he spent
        # Hiding bought a log entry and nothing else. `concealment` folds
        # it from the fight the same way `slot_allocation`,
        # `spent_charges` and `actor_holding` are folded just above, and
        # for the same reason -- it lives in the fight, not in the caller.
        concealment=concealment_for(session, observer_id=actor_id),
        # WHO IS ON HIS SIDE. Enumeration had only ever been handed
        # ENEMIES, so an ally-targeted offer had nothing to name --- Aid
        # and Healing surface with `target_id=None` for exactly that
        # reason. Stabilizing a dying man (6E2 p.109) cannot: the roll's
        # difficulty depends on WHICH man is bleeding. Already computed
        # just below for the PhaseSituation.
        # STANDING AND FALLEN BOTH. `allies_of` excludes the down,
        # which is right for "who can help me fight" and exactly wrong
        # for the man on the ground who needs somebody to kneel beside
        # him.
        allies=roster.allies_of(actor) + roster.fallen_allies_of(actor),
    )
    if not menu:
        session, spent = _mark_acted(session, actor_id)
        return PhaseResult(
            encounter=_with(encounter, session), actor_id=actor_id,
            events=session.event_log[log_before:],
            notes=[f"{actor_id} had no legal action"],
        )

    situation = PhaseSituation(
        actor=actor, menu=menu, enemies=enemies,
        allies=roster.allies_of(actor),
        # THE MAN ON THE GROUND, kept in his own list. The menu above
        # already gets standing and fallen both; this object did not, so
        # the tactic layer could not see the ally it was supposed to
        # save and `stabilize` was offered 39 times and chosen never.
        # A separate field rather than a widened `allies` because three
        # tactics read that one as "who can help me fight".
        fallen_allies=roster.fallen_allies_of(actor),
        # THE SAME DISTANCES THE MENU WAS BUILT FROM. Computed once above
        # for `enumerate_actions` and handed on rather than measured
        # twice, so a tactic and the offer it names cannot disagree about
        # who is adjacent.
        distances_m=dict(distances or {}),
        reach_m=float(getattr(actor.combat_stats(), "reach_m", 1.0)),
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
        session, spent = _mark_acted(session, actor_id)
        return PhaseResult(
            encounter=_with(encounter, session), actor_id=actor_id, action_id=action.action_id,
            kind=action.kind, skipped_kind=action.kind,
            events=session.event_log[log_before:],
            notes=[f"no resolver for {action.kind!r}; Phase spent"],
        )

    session, spent = _mark_acted(resolved.session, actor_id)
    return PhaseResult(
        encounter=_with(encounter, session), actor_id=actor_id,
        action_id=action.action_id, kind=action.kind,
        result=resolved.result,
        events=session.event_log[log_before:],
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

    phases = 0
    turns = 0

    verdict = Roster(encounter.sessions[0]).decide(stop)
    if verdict:
        return EncounterResult(
            encounter=encounter, complete=True, winner=verdict.winner,
            notes=["fight was already decided before the first Phase"],
        )

    # NO SECOND COPY OF THE ADVANCE. This used to resolve the Segment's
    # order, spend every slot in it, and call `advance_segment` itself,
    # which is why `run_phase` stopped dead at the end of a Segment and a
    # consumer stepping by Phase could not finish a fight. All of that
    # lives in `run_phase` now; what is left here is what a DRIVER owns:
    # how many Turns to allow, when to call a fight stalled, and who won.
    quiet = 0
    while turns < max_turns:
        start_turn = encounter.turn

        phase = run_phase(
            encounter, chooser, roller=roller,
            on_unresolvable=on_unresolvable, campaign=campaign, until=stop,
        )
        before = encounter.sessions[0]
        encounter = phase.encounter
        turns += encounter.turn - start_turn

        if phase.actor_id is None:
            # The only `actor_id=None` there is: the fight is decided.
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
        if _something_happened(before, phase.session):
            quiet = 0
        else:
            quiet += 1
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

    verdict = Roster(encounter.sessions[0]).decide(stop)
    if verdict:
        return EncounterResult(
            encounter=encounter, turns=turns, phases=phases,
            complete=True, winner=verdict.winner, skipped_kinds=skipped,
        )
    return EncounterResult(
        encounter=encounter, turns=turns, phases=phases,
        complete=False, winner=None, skipped_kinds=skipped,
        notes=[f"stopped at the {max_turns}-Turn guard without a decision"],
    )


#: Events that mean something happened TO SOMEBODY, whatever the numbers
#: on them. Deliberately not `ActionResolved`: aiming, holding and
#: shuffling a Multipower all resolve cleanly and change nothing anybody
#: would notice.
_PROGRESS_EVENTS = frozenset({
    "MovementResolved", "StatusChanged", "StatusEffectsChanged",
    "PresenceApplied", "EntangleApplied", "FlashApplied",
    "AdjustmentApplied", "ConstructDamaged",
})

#: Events that mean something happened only when their numbers are not
#: zero: kind -> the fields that have to move. A man at full STUN takes a
#: free Post-Segment 12 Recovery of nothing every Turn (6E2 p.131), and
#: counting that as progress is what let a fight of two men aiming at each
#: other for forty Turns look busy -- the wrap reset the stalemate counter
#: every twelve Segments. It only became visible when `run_phase` took
#: over the advance and those rows started arriving inside a Phase.
_PROGRESS_IF_NONZERO = {
    "VitalsChanged": ("stun", "body", "end"),
    "RecoveryTaken": ("stun_recovered", "end_recovered"),
    "BleedingSuffered": ("body_lost", "stun_lost"),
}


def _something_happened(before: "CombatSession", after: "CombatSession") -> bool:
    """Did this Phase move the fight at all?

    Reads the events the Phase ADDED rather than comparing state, because
    a Phase that hurt somebody and healed them back still happened.

    Damage used to be read out of `ActionResolved.result_payload`, a
    free-form dict. It has its own typed row now (`VitalsChanged`), so
    this asks the event that says a vital moved rather than parsing the
    one that says what was rolled.
    """
    for event in after.event_log[len(before.event_log):]:
        kind = getattr(event, "kind", "")
        if kind in _PROGRESS_EVENTS:
            return True
        fields = _PROGRESS_IF_NONZERO.get(kind)
        if fields and any(int(getattr(event, f, 0) or 0) for f in fields):
            return True
    return False
