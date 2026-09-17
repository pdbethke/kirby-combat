"""A fight rebuilt from nothing but its rows is the same fight, vitals and all.

THE DEFECT THIS PINS. `tests/loop/test_replay_reproduces_the_loop.py`
(beside this file) proved the loop's own DECISIONS survive a replay ---
whose Phase it is, and which slots are spent. It could not prove anything
about the men, because `apply_event` folded no STUN, no BODY and no END:
every resolver changed the combatant BESIDE the event that described the
change ("mutate-then-log"), so a consumer that persists only the rows
rebuilt a fight in which nobody had ever been hit. Measured on the
consumer: after two Phases a fighter stood at 27 STUN in the fight that
ran and 50 STUN in the fight replayed from its log.

So this file asks the question the other one cannot: at EVERY sequence of
a whole fight, does the replayed session hold the same vitals, and the
same next actor, as the fight that ran, rewound to that same point?

And the second half asks it the way a consumer actually steps a fight:
one Phase at a time, throwing the session away between steps and
rebuilding it from the rows alone. Same winner, same log.
"""
from __future__ import annotations

from dataclasses import replace

from conftest import fighter  # tests/loop/conftest.py

from kirby_combat.encounter import Encounter
from kirby_combat.loop import FirstLegalChooser, next_actor_id, run_phase
from kirby_combat.loop.run import run_encounter
from kirby_combat.roster import LastSideStanding, Roster
from kirby_combat.session import CombatSession, apply_event
from kirby_combat.session.rewind import rewind_to_sequence
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()

#: The seeds are the "same inputs" half of the claim: a replay is only
#: meaningful against a fight whose inputs can be stated.
FIGHT_SEED = 11
SESSION_SEED = 7

MAX_TURNS = 8


def _combatants():
    """Three fighters, built fresh each call --- two against one, so the
    fight actually reaches `last_side_standing` inside the Turn guard."""
    return [
        fighter("a", side=Side.named("blue"), dex=20),
        fighter("b", side=Side.named("red"), dex=15),
        fighter("c", side=Side.named("red"), dex=11),
    ]


def _fresh_session() -> CombatSession:
    return CombatSession.create(
        id="s", combatants=_combatants(), scene=None, template=TEMPLATE,
        dice_roller=RandomRoller(seed=SESSION_SEED),
    )


def _encounter() -> Encounter:
    return Encounter(
        id="e", turn=1, segment=12, sessions=[_fresh_session().start()],
    )


def _vitals(session: CombatSession) -> dict[str, tuple[int, int, int]]:
    """Every folded stat, for every combatant, in one comparable shape."""
    return {
        cid: (
            c.state.current_stun, c.state.current_body, c.state.current_end,
        )
        for cid, c in sorted(session.combatants.items())
    }


def _shape(event) -> tuple:
    """An event without its identity --- ids and timestamps are fresh on
    every run and say nothing about whether the two fights agree.

    `ActionResolved` is compared by its WHOLE payload, not just its kind.
    That is where a maneuver's own facts live --- a Trip's
    `is_prone_after`, an activation roll, the CVs the blow was really made
    against --- and comparing kinds alone is what let a resolver edit a
    committed row with both of these tests green.
    """
    fields = {
        "ActionResolved": ("result_payload",),
        "PhaseSpent": ("combatant_id", "segment", "turn", "reason"),
        "ActingOrderResolved": ("order", "segment", "turn"),
        "SegmentAdvanced": ("from_segment", "to_segment", "to_turn"),
        "ActionDeclared": ("combatant_id", "action_type", "targets"),
        "VitalsChanged": ("combatant_id", "stun", "body", "end", "reason"),
        "RecoveryTaken": ("combatant_id", "stun_recovered", "end_recovered"),
        "BleedingSuffered": ("combatant_id", "body_lost", "stun_lost", "rule"),
    }.get(event.kind, ())
    return (event.kind, *(repr(getattr(event, f)) for f in fields))


def _ran_the_whole_fight():
    """The live fight: one roller, one `run_encounter`, run to a verdict."""
    result = run_encounter(
        _encounter(), FirstLegalChooser(),
        roller=RandomRoller(seed=FIGHT_SEED),
        max_turns=MAX_TURNS, on_unresolvable="skip",
    )
    assert result.complete, (
        f"the fight must actually finish for this to mean anything: "
        f"{result.notes}"
    )
    return result


# ---------------------------------------------------------------------------
# (1) Every sequence, every stat
# ---------------------------------------------------------------------------

def test_the_fight_hurts_somebody():
    """The negative control. If nobody's vitals ever move, the equivalence
    below is satisfied by two fights in which nothing happened."""
    live = _ran_the_whole_fight().encounter.sessions[0]
    start = _vitals(_fresh_session())

    assert _vitals(live) != start


def test_replaying_the_log_reproduces_every_vital_at_every_sequence():
    live = _ran_the_whole_fight().encounter.sessions[0]

    replayed = _fresh_session()
    for event in live.event_log:
        replayed = apply_event(replayed, event)
        rewound = rewind_to_sequence(live, event.sequence)

        assert _vitals(replayed) == _vitals(rewound), (
            f"vitals diverge at sequence {event.sequence} ({event.kind})"
        )
        assert next_actor_id(replayed) == next_actor_id(rewound), (
            f"next actor diverges at sequence {event.sequence} ({event.kind})"
        )


def test_the_replayed_fight_ends_where_the_live_one_did():
    result = _ran_the_whole_fight()
    live = result.encounter.sessions[0]

    replayed = _fresh_session()
    for event in live.event_log:
        replayed = apply_event(replayed, event)

    assert _vitals(replayed) == _vitals(live)
    assert Roster(replayed).decide(LastSideStanding()).winner == result.winner


# ---------------------------------------------------------------------------
# (2) Stepping the fight the way a consumer steps it
# ---------------------------------------------------------------------------

def _stepped_one_phase_at_a_time():
    """Rehydrate from the rows, take ONE Phase, throw the session away.

    This is the consumer's whole loop: it holds no session between steps,
    only the rows it has persisted. The roller is deliberately the same
    object across steps --- dice are not state the log carries, and the
    claim is about the fight, not about the random stream.
    """
    roller = RandomRoller(seed=FIGHT_SEED)
    chooser = FirstLegalChooser()
    stop = LastSideStanding()
    rows: list = list(_encounter().sessions[0].event_log)
    winner = None

    for _ in range(MAX_TURNS * 12 * 12):
        session = _fresh_session()
        for event in rows:
            session = apply_event(session, event)
        encounter = Encounter(
            id="e", turn=session.timeline.turn,
            segment=session.timeline.segment, sessions=[session],
        )

        phase = run_phase(
            encounter, chooser, roller=roller, on_unresolvable="skip",
        )
        rows = list(phase.session.event_log)
        if phase.actor_id is None:
            break
        verdict = Roster(phase.session).decide(stop)
        if verdict:
            winner = verdict.winner
            break
    else:                                   # pragma: no cover - guard
        raise AssertionError("the stepped fight never finished")

    return winner, rows


def test_stepping_by_replay_reaches_the_same_winner_and_the_same_log():
    result = _ran_the_whole_fight()
    live_rows = result.encounter.sessions[0].event_log

    winner, stepped_rows = _stepped_one_phase_at_a_time()

    assert winner == result.winner
    assert any(e.kind == "ActionResolved" for e in live_rows), (
        "no resolution in the log, so the payload comparison proves nothing")
    assert [_shape(e) for e in stepped_rows] == [_shape(e) for e in live_rows]
