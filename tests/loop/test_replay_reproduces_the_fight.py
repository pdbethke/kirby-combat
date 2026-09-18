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


from conftest import fighter  # tests/loop/conftest.py

from kirby_combat.encounter import Encounter
from kirby_combat.loop import FirstLegalChooser, next_actor_id, run_phase
from kirby_combat.loop.run import run_encounter
from kirby_combat.roster import LastSideStanding, Roster
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)
from kirby_combat.session import CombatSession, apply_event
from kirby_combat.session.rewind import rewind_to_sequence
from kirby_combat.session.state_view import state_view
from kirby_combat.side import Side
from kirby_combat.statuses import statuses_for
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()

#: The seeds are the "same inputs" half of the claim: a replay is only
#: meaningful against a fight whose inputs can be stated.
FIGHT_SEED = 11
SESSION_SEED = 7

MAX_TURNS = 8


class CloseTheDistanceThenFight:
    """Take a step the first time you act, then fight.

    `FirstLegalChooser` picks the first offer on the menu and that offer
    is always `attack`, so a fight driven by it never moves anybody ---
    which would make this file's position claim true of a fold that
    writes nothing. This chooser moves each man once and then behaves
    exactly like `FirstLegalChooser`. It rolls nothing: the decision is
    a function of who is acting and whether he has already moved, so the
    fight it drives is as reproducible as the one `FirstLegalChooser`
    drives.
    """

    def __init__(self) -> None:
        self._moved: set[str] = set()

    def choose(self, situation):
        actor_id = str(situation.actor.id)
        if actor_id not in self._moved:
            move = next(
                (m for m in situation.menu if m.kind == "move"), None)
            if move is not None:
                self._moved.add(actor_id)
                return move.action_id
        return situation.menu[0].action_id


def _combatants():
    """Three fighters, built fresh each call --- two against one, so the
    fight actually reaches `last_side_standing` inside the Turn guard."""
    return [
        fighter("a", side=Side.named("blue"), dex=20),
        fighter("b", side=Side.named("red"), dex=15),
        fighter("c", side=Side.named("red"), dex=11),
    ]


#: WHERE THE THREE OF THEM START. A fight with no Scene is a fight in
#: which nobody can move, so the position half of this file's claim would
#: be satisfied by three men standing still --- the exact failure the
#: vitals half was written to catch.
#: Far enough apart that a half-move toward the other side is on every
#: menu, and facing each other so that a move which turns a man shows up
#: as a change of facing and not only of place.
START = {
    "a": Position(1.0, 0.0, 0.0, 0.0),
    "b": Position(21.0, 0.0, 0.0, 3.14),
    "c": Position(21.0, 4.0, 0.0, 3.14),
}


def _scene() -> Scene:
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-5.0, -5.0, 0.0, 400.0, 400.0, 14.0),
        surfaces=[Surface(
            id="g", name="g",
            polygon_xy=[(-5, -5), (400, -5), (400, 400), (-5, 400)],
            elevation_m=0.0, surface_type="ground", cover_level=0,
        )],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions=dict(START),
    )


def _fresh_session() -> CombatSession:
    return CombatSession.create(
        id="s", combatants=_combatants(), scene=_scene(), template=TEMPLATE,
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


def _places(session: CombatSession) -> dict[str, tuple]:
    """Where every man stands and which way he faces, in one comparable
    shape.

    FACING IS IN IT: a `Position` carries it ("0 rad = east") and a board
    draws it, so a replay that put a man on the right spot pointing the
    wrong way is not the same fight.
    """
    positions = (getattr(session.scene, "combatant_positions", None) or {})
    return {
        cid: (round(p.x, 6), round(p.y, 6), round(p.z, 6), round(p.facing, 6))
        for cid, p in sorted(positions.items())
    }


def _recorded(session: CombatSession) -> dict[str, frozenset[str]]:
    """What the RECORD says --- `CombatSession.statuses`, folded by
    `apply_event` out of the `StatusEffectsChanged` rows."""
    return dict(sorted(session.statuses.items()))


def _conditions(session: CombatSession) -> dict[str, frozenset[str]]:
    """Every condition every man is in --- knocked out, stunned, prone,
    held, entangled, flashed --- asked of the session, per combatant."""
    return {
        cid: statuses_for(session, cid)
        for cid in sorted(session.combatants)
    }


def _view(session: CombatSession) -> tuple:
    """The whole published projection, minus the one field that is a roll.

    `state_view` requires a roller because the perception fold rolls for
    two pair kinds; those two are not a projection of the log. Every
    other field is a read, and that is what is compared --- both sides
    are handed a roller seeded the same way, so even the rolled field
    agrees when the fight does.
    """
    view = state_view(session, roller=RandomRoller(seed=99))
    return (
        view.status, view.turn, view.segment, view.last_sequence,
        view.next_actor_id,
        tuple(
            (c.id, c.current_stun, c.current_body, c.current_end,
             c.health, c.down, c.position, c.prone, c.stunned, c.ko,
             c.invisible, tuple(c.perceives))
            for c in view.combatants
        ),
    )


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
        "MovementResolved": ("combatant_id", "from_pos", "to_pos", "move_type"),
        "StatusEffectsChanged": ("combatant_id", "added", "removed"),
    }.get(event.kind, ())
    return (event.kind, *(repr(getattr(event, f)) for f in fields))


def _ran_the_whole_fight():
    """The live fight: one roller, one `run_encounter`, run to a verdict."""
    result = run_encounter(
        _encounter(), CloseTheDistanceThenFight(),
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


def test_somebody_moves_in_this_fight():
    """The negative control for POSITIONS. Three men who never take a step
    make the position equivalence below true of any two fights, including
    two in which the fold does nothing at all --- which is exactly the
    state `MovementResolved` was in."""
    live = _ran_the_whole_fight().encounter.sessions[0]

    assert any(e.kind == "MovementResolved" for e in live.event_log), (
        "nobody moved, so the position claim below proves nothing")
    assert _places(live) != _places(_fresh_session()), (
        "every man is where he started, so the position claim below is "
        "satisfied by a fold that writes nothing")


def test_somebody_goes_down_in_this_fight():
    """The negative control for CONDITIONS. A fight in which nobody is
    ever knocked out, stunned or put on the ground makes the condition
    equivalence below true of two empty status sets."""
    live = _ran_the_whole_fight().encounter.sessions[0]

    landed = set().union(*_conditions(live).values())
    assert landed, (
        "nobody ended the fight in any condition at all, so the condition "
        f"claim below proves nothing (sets were {_conditions(live)})")


def test_a_condition_reaches_the_log_as_a_row():
    """THE SECOND DEFECT THIS FILE PINS. Conditions were derived from the
    log and never written TO it: `StatusEffectsChanged` had no producer
    anywhere in the engine (its only door,
    `status_emission.apply_event_with_deltas`, was called by nothing) and
    `StatusChanged` had none either. So a viewer reading the rows could
    not know a man had gone down --- it could only know if it re-ran this
    engine's whole derivation itself.

    `run_phase` writes them down now, through the one door."""
    live = _ran_the_whole_fight().encounter.sessions[0]

    rows = [e for e in live.event_log if e.kind == "StatusEffectsChanged"]
    assert rows, "no condition in this fight was ever written down"
    assert any("knockedOut" in e.added for e in rows), (
        f"nobody was recorded going down; the rows said "
        f"{[(e.combatant_id, sorted(e.added), sorted(e.removed)) for e in rows]}")


def test_the_record_says_what_the_rule_says():
    """The fold is not a second opinion.

    `statuses_for` is the RULE --- what makes a condition true ---  and
    `session.statuses` is the RECORD of it, folded out of the rows. A
    record that quietly drifted from the rule would satisfy every
    live-versus-replayed comparison in this file, because both sides
    would drift the same way. So they are compared to each other, at
    every Phase boundary of a whole fight.
    """
    _live, observed = _ran_it_and_wrote_down_what_it_saw()

    assert observed, "no observations"
    for sequence, (_v, _a, _p, rule, record) in observed.items():
        assert rule == record, (
            f"the record and the rule disagree at sequence {sequence}: "
            f"rule {rule}, record {record}"
        )


def _ran_it_and_wrote_down_what_it_saw():
    """The live fight, stepped by `run_phase`, RECORDING the state after
    every Phase as it happens.

    THE ANCHOR. Comparing a replay against `rewind_to_sequence` compares
    two replays: `rewind_to_sequence` is itself a fresh session with the
    log played through `apply_event`, so a fold error that affects both
    sides identically is invisible at every intermediate point. These
    recordings are taken from the LIVE session, mid-fight, before any
    replay exists --- so the comparison has something outside the fold to
    be right about.

    Keyed by sequence number: after each Phase, the state at the sequence
    that Phase's last event carries.
    """
    roller = RandomRoller(seed=FIGHT_SEED)
    chooser = CloseTheDistanceThenFight()
    encounter = _encounter()
    stop = LastSideStanding()
    observed: dict[int, tuple] = {}

    for _ in range(MAX_TURNS * 12 * 12):
        phase = run_phase(encounter, chooser, roller=roller,
                          on_unresolvable="skip")
        if phase.actor_id is None:
            break
        encounter = phase.encounter
        live = phase.session
        observed[len(live.event_log)] = (
            _vitals(live), next_actor_id(live), _places(live),
            _conditions(live), _recorded(live),
        )
        if Roster(live).decide(stop):
            break
    else:                                   # pragma: no cover - guard
        raise AssertionError("the live fight never finished")

    return encounter.sessions[0], observed


def test_replaying_the_log_reproduces_what_the_live_fight_showed():
    """Anchored to the live session, not to another replay."""
    live, observed = _ran_it_and_wrote_down_what_it_saw()
    assert len(observed) >= 4, "too few observations to mean anything"
    seen = [o[0] for o in observed.values()]
    assert seen[0] != seen[-1], (
        "nobody's vitals moved across the observations, so the comparison "
        "below would hold for two fights in which nothing happened")

    replayed = _fresh_session()
    for event in live.event_log:
        replayed = apply_event(replayed, event)
        if event.sequence not in observed:
            continue
        seen_vitals, seen_actor, seen_places, seen_cond, seen_record = (
            observed[event.sequence])

        assert _vitals(replayed) == seen_vitals, (
            f"vitals diverge at sequence {event.sequence} ({event.kind}) "
            f"from what the live fight showed"
        )
        assert next_actor_id(replayed) == seen_actor, (
            f"next actor diverges at sequence {event.sequence} "
            f"({event.kind}) from what the live fight showed"
        )
        assert _places(replayed) == seen_places, (
            f"positions diverge at sequence {event.sequence} "
            f"({event.kind}) from what the live fight showed"
        )
        assert _conditions(replayed) == seen_cond, (
            f"conditions diverge at sequence {event.sequence} "
            f"({event.kind}) from what the live fight showed"
        )
        assert _recorded(replayed) == seen_record, (
            f"the recorded conditions diverge at sequence "
            f"{event.sequence} ({event.kind}) from what the live fight "
            f"showed"
        )
        assert _view(replayed) == _view(rewind_to_sequence(live, event.sequence)), (
            f"the state view diverges at sequence {event.sequence} "
            f"({event.kind})"
        )


def test_replaying_the_log_reproduces_every_vital_at_every_sequence():
    """The same claim at EVERY sequence, including the ones no Phase ended
    on --- the Recovery rows, the Segment advances, each row of a Turn
    wrap.

    Against `rewind_to_sequence`, which is itself a replay: this is the
    finer-grained half and it is anchored by the test above rather than
    standing on its own. Both are needed. This one alone would compare two
    replays; that one alone would skip every sequence inside a Phase.
    """
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
        assert _places(replayed) == _places(rewound), (
            f"positions diverge at sequence {event.sequence} ({event.kind})"
        )
        assert _conditions(replayed) == _conditions(rewound), (
            f"conditions diverge at sequence {event.sequence} ({event.kind})"
        )
        assert _view(replayed) == _view(rewound), (
            f"the state view diverges at sequence {event.sequence} "
            f"({event.kind})"
        )


def test_the_replayed_fight_ends_where_the_live_one_did():
    result = _ran_the_whole_fight()
    live = result.encounter.sessions[0]

    replayed = _fresh_session()
    for event in live.event_log:
        replayed = apply_event(replayed, event)

    assert _vitals(replayed) == _vitals(live)
    assert _places(replayed) == _places(live)
    assert _conditions(replayed) == _conditions(live)
    assert _view(replayed) == _view(live)
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
    chooser = CloseTheDistanceThenFight()
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
