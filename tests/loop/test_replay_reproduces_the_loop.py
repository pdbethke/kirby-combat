"""A fight rebuilt from nothing but its log picks the same man to act.

THE DEFECT THIS PINS. The loop's own decisions -- who acts in what order
this Segment, and whose slot has been spent -- were made in memory and
told nobody. Everything else a fight does reaches the event log; those two
did not. A consumer that persists the log and only the log (which is what
an append-only record means) could therefore rebuild a fight, ask it whose
Phase it was, and be told nobody's: an empty acting order, forever.

So this is not a test of `apply_event`'s new branches. It is a test that
the two paths agree -- the fight that RAN and the fight REBUILT from what
the fight that ran wrote down. The rebuilt session gets fresh combatants,
a fresh roller and an EMPTY log; the only thing it is given is the events.
"""
from __future__ import annotations

from conftest import fighter  # tests/loop/conftest.py

from kirby_combat.encounter import Encounter
from kirby_combat.enumeration import is_down
from kirby_combat.loop import (
    FirstLegalChooser, next_actor_id, resolve_next_actor, run_phase,
)
from kirby_combat.session import CombatSession, apply_event
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()

#: The seeds are the "same inputs" half of the claim: a replay is only
#: meaningful against a fight whose inputs can be stated.
TIE_SEED = 99
PHASE_SEED = 3
NEXT_PHASE_SEED = 5


def _combatants():
    """Three fighters, built fresh each call.

    Fresh rather than shared, because the rebuilt session must not be
    handed the very objects the original fight has already damaged --- that
    would prove nothing about the log.
    """
    return [
        fighter("a", side=Side.named("blue"), dex=20),
        fighter("b", side=Side.named("red"), dex=15),
        fighter("c", side=Side.named("red"), dex=11),
    ]


def _started(combatants) -> CombatSession:
    return CombatSession.create(
        id="s", combatants=combatants, scene=None, template=TEMPLATE,
        dice_roller=RandomRoller(seed=7),
    ).start()


def _encounter_for(session: CombatSession) -> Encounter:
    """The clock this session is standing on. `run_phase` takes an
    `Encounter` --- it owns the Segment advance as well as the Phase ---
    and a session's own Timeline says where it is."""
    return Encounter(
        id="e", turn=session.timeline.turn, segment=session.timeline.segment,
        sessions=[session],
    )


def _ran_a_segment_and_a_phase() -> CombatSession:
    """One Segment's order resolved, one Phase run. The original fight."""
    encounter = Encounter(
        id="e", turn=1, segment=12, sessions=[_started(_combatants())],
    )
    tie_roller = RandomRoller(seed=TIE_SEED)
    # Resolved explicitly, with its own seeded tie-roller, so this file's
    # "same inputs" claim stays stateable. `run_phase` would resolve one
    # itself if the session were carrying none; it leaves this one alone.
    encounter = encounter.run_segment(roller=lambda: tie_roller.roll_dice(3))
    phase = run_phase(
        encounter, FirstLegalChooser(),
        roller=RandomRoller(seed=PHASE_SEED),
    )
    assert phase.actor_id is not None, "the fight must actually have acted"
    return phase.session


def _rebuilt_from(original: CombatSession) -> CombatSession:
    """A session built from the same inputs and NOTHING but the events."""
    rebuilt = CombatSession.create(
        id="s", combatants=_combatants(), scene=None, template=TEMPLATE,
        dice_roller=RandomRoller(seed=7),
    )
    assert rebuilt.event_log == []
    for event in original.event_log:
        rebuilt = apply_event(rebuilt, event)
    return rebuilt


def _spent(session: CombatSession) -> dict[str, bool]:
    return {s.combatant_id: s.has_acted for s in session.timeline.acting_order}


def test_the_loops_decisions_are_in_the_log():
    """The negative control for everything below.

    If these two kinds are not in the log, the replay tests pass by
    replaying a fight in which nothing was ever decided.
    """
    original = _ran_a_segment_and_a_phase()
    kinds = [e.kind for e in original.event_log]

    assert kinds.count("ActingOrderResolved") == 1
    assert kinds.count("PhaseSpent") == 1


def test_a_replayed_fight_is_standing_where_the_original_stood():
    original = _ran_a_segment_and_a_phase()
    rebuilt = _rebuilt_from(original)

    assert next_actor_id(rebuilt) == next_actor_id(original)
    assert _spent(rebuilt) == _spent(original)
    assert [s.combatant_id for s in rebuilt.timeline.acting_order] == \
        [s.combatant_id for s in original.timeline.acting_order]
    assert (rebuilt.timeline.segment, rebuilt.timeline.turn) == \
        (original.timeline.segment, original.timeline.turn)


def test_the_next_phase_runs_the_same_on_both():
    """The claim that matters: the replayed fight goes on being the fight."""
    original = _ran_a_segment_and_a_phase()
    rebuilt = _rebuilt_from(original)

    from_original = run_phase(
        _encounter_for(original), FirstLegalChooser(),
        roller=RandomRoller(seed=NEXT_PHASE_SEED),
    )
    from_rebuilt = run_phase(
        _encounter_for(rebuilt), FirstLegalChooser(),
        roller=RandomRoller(seed=NEXT_PHASE_SEED),
    )

    assert from_rebuilt.actor_id == from_original.actor_id
    assert from_rebuilt.actor_id is not None
    assert from_rebuilt.action_id == from_original.action_id
    assert [e.kind for e in from_rebuilt.events] == \
        [e.kind for e in from_original.events]


def test_a_spent_phase_is_spent_in_the_replay_too():
    """Without `PhaseSpent` the replay hands the same man every Phase.

    Stated separately from the state comparison above because it is the
    failure that was actually observed: a rehydrated fight whose order was
    restored but whose spends were not would return the FIRST man in the
    order forever, and the fight would never reach the second.
    """
    original = _ran_a_segment_and_a_phase()
    acted = [s.combatant_id for s in original.timeline.acting_order if s.has_acted]
    assert acted, "the original fight spent a Phase"

    rebuilt = _rebuilt_from(original)

    assert next_actor_id(rebuilt) not in acted


# ---------------------------------------------------------------------------
# The man who cannot use the Phase he has
# ---------------------------------------------------------------------------

def _knocked_out(session: CombatSession, combatant_id: str) -> CombatSession:
    """Put a man on the ground the way a resolver's damage would.

    STUN at 0 is 6E1 p.421's "knocked out", which is what `is_down` reads.
    """
    session.combatants[combatant_id].state.current_stun = 0
    return session


def test_the_replay_skips_the_downed_man_the_original_skipped():
    """The skip is a spend, and it has to be in the log to survive.

    THE MAN HERE IS KNOCKED OUT OFF THE RECORD, deliberately --- his STUN
    is set by hand, with no event, which is how the original defect was
    reproduced. `apply_event` folds vitals now (2026-09-17), so a fight
    hurt the ordinary way IS hurt in the replay; this test keeps the
    harder version of the claim, where the replay has no idea anyone is
    down and must still pass over him. The ONLY thing that can carry that
    is the spend the original wrote down. Before `PhaseSpent(reason=
    "down")` nothing did, and the two fights reached different men: the
    original `c`, the replay `b`.
    """
    original = _ran_a_segment_and_a_phase()   # "a" has acted
    original = _knocked_out(original, "b")

    original, actor_id, skips = resolve_next_actor(original)

    assert actor_id == "c"
    assert [(e.kind, e.combatant_id, e.reason) for e in skips] == \
        [("PhaseSpent", "b", "down")]
    assert any(e.kind == "PhaseSpent" and e.reason == "down"
               for e in original.event_log)

    rebuilt = _rebuilt_from(original)

    # The replay has no idea THIS man is hurt -- he was put down off
    # the record -- which is the point.
    assert not is_down(rebuilt.combatants["b"])
    assert next_actor_id(rebuilt) == next_actor_id(original) == "c"


def test_the_skip_rides_out_on_the_phase_result():
    """A consumer persists what a `PhaseResult` hands it, and no more."""
    original = _knocked_out(_ran_a_segment_and_a_phase(), "b")

    phase = run_phase(
        _encounter_for(original), FirstLegalChooser(),
        roller=RandomRoller(seed=NEXT_PHASE_SEED),
    )

    assert phase.actor_id == "c"
    assert [(e.kind, e.combatant_id, e.reason) for e in phase.events
            if e.kind == "PhaseSpent"] == \
        [("PhaseSpent", "b", "down"), ("PhaseSpent", "c", "acted")]


def test_asking_who_is_next_does_not_change_the_fight():
    """`next_actor_id` is a question. It used to be a move.

    It spent the slot of everyone it passed over, in place and off the
    log, so a reader asking whose Phase it was altered the fight.
    """
    original = _knocked_out(_ran_a_segment_and_a_phase(), "b")
    before = [(s.combatant_id, s.has_acted) for s in original.timeline.acting_order]
    log_length = len(original.event_log)

    assert next_actor_id(original) == "c"

    assert [(s.combatant_id, s.has_acted)
            for s in original.timeline.acting_order] == before
    assert len(original.event_log) == log_length
