"""The readable projection of a rewound session — the engine's own readings.

A viewer folds the event log for display and must be checkable against the
engine's fold. This is the shape it is checked against, and every value on
it is read through the engine's own function: `classify_health` for the
rung, `is_down` for whether he is still in it, `Side.of` for whose part he
is on. A second reading here would be the thing the check exists to catch.
"""
from __future__ import annotations

import dataclasses

from kirby_combat import state_view
from kirby_combat.health import classify_health
from kirby_combat.enumeration import is_down
from kirby_combat.side import Side

from tests.combat_fixtures import (
    a_fight_that_has_happened, flashed_session, placed_session,
    two_fighter_session,
)


def test_the_view_reads_the_clock_and_the_status_off_the_session():
    session = two_fighter_session()

    view = state_view(session)

    assert view.status == session.status
    assert view.turn == session.timeline.turn
    assert view.segment == session.timeline.segment


def test_last_sequence_is_the_last_event_not_the_log_length():
    """A log holding only `SessionStarted` is a fight nothing has happened
    in, and answers 0 — as does a session still in setup, whose log is
    empty. Read off the last event rather than counted from the length."""
    session = two_fighter_session()

    assert state_view(session).last_sequence == 0
    assert state_view(session.start()).last_sequence == 0
    assert state_view(a_fight_that_has_happened()).last_sequence == (
        a_fight_that_has_happened().event_log[-1].sequence
    )


def test_every_combatant_is_projected_through_the_engines_own_readings():
    session = two_fighter_session()

    view = state_view(session)

    assert len(view.combatants) == len(session.combatants)
    for c in view.combatants:
        live = session.combatants[c.id]
        assert c.name == str(live.name)
        assert c.health == classify_health(live)
        assert c.down == is_down(live)
        side = Side.of(live)
        assert c.side == (None if side.is_solo else side.id)
        assert c.current_stun == int(live.current_stun)
        assert c.current_body == int(live.current_body)
        assert c.current_end == int(live.current_end)


def test_the_view_carries_where_he_is_and_which_way_he_faces():
    """`position_of` is the door. A combatant not on the map reads None —
    NOT the origin, which would put him adjacent to whoever stands at
    (0, 0, 0) in every distance a consumer computes off this."""
    session = placed_session()

    view = state_view(session)

    alice = next(c for c in view.combatants if c.id == "alice")
    assert (alice.position.x, alice.position.y, alice.position.z) == (0.0, 0.0, 0.0)
    assert alice.position.facing == 0.0

    assert next(
        c for c in state_view(two_fighter_session()).combatants
    ).position is None


def test_the_conditions_come_from_the_one_status_door():
    """`statuses_for` folds every condition source out of the log — Prone
    from a Trip's payload, Stunned from a resolution, Knocked Out from
    both a payload and the vitals. Reading any one of those sources here
    instead would be a second fold of the same fact."""
    from kirby_combat.statuses import KNOCKED_OUT, PRONE, STUNNED, statuses_for

    session = a_fight_that_has_happened()

    for c in state_view(session).combatants:
        held = statuses_for(session, c.id)
        assert c.prone == (PRONE in held)
        assert c.stunned == (STUNNED in held)
        assert c.ko == (KNOCKED_OUT in held)


def test_the_next_actor_is_a_question_and_spends_no_slot():
    from kirby_combat import next_actor_id

    session = a_fight_that_has_happened()

    before = [s.has_acted for s in session.timeline.acting_order]
    view = state_view(session)

    assert view.next_actor_id == next_actor_id(session)
    assert [s.has_acted for s in session.timeline.acting_order] == before


def test_a_man_nobody_can_see_is_absent_from_the_observers_perceives():
    """THE PERCEPTION CASE, and the reason fog stops failing open.

    A viewer used to filter the board from a per-segment audit row the
    consuming service wrote, and with no row the fog failed OPEN — the
    view showed EVERYONE while claiming to show one man's eyes. The
    engine already owns this answer: `cannot_perceive` is the ONE
    predicate 6E2 p.127 / p.9 go through, and it folds a Flash on the
    observer's Sense Group, a Darkness field on the ray, Invisibility and
    the walls all at once. This surfaces it; it decides nothing.

    Flash is the clean lever because it needs no geometry: a fighter
    Flashed in the Sight Group perceives nobody, and everyone still
    perceives him.
    """
    session = flashed_session()

    view = state_view(session)

    blinded = next(c for c in view.combatants if c.id == "alice")
    other = next(c for c in view.combatants if c.id == "bob")
    assert blinded.perceives == []
    assert "alice" in other.perceives


def test_nobody_perceives_himself():
    """`perceives` is who ELSE he can see. Including himself would make
    every consumer subtract him again."""
    for c in state_view(two_fighter_session()).combatants:
        assert c.id not in c.perceives


def test_the_view_is_frozen_and_flat():
    """Nothing on it is a live engine object: a viewer serialises it."""
    view = state_view(two_fighter_session())
    assert dataclasses.is_dataclass(view)
    fields = {f.name for f in dataclasses.fields(view)}
    assert fields == {
        "status", "turn", "segment", "last_sequence", "next_actor_id",
        "combatants",
    }
    combatant_fields = {f.name for f in dataclasses.fields(view.combatants[0])}
    assert combatant_fields == {
        "id", "name", "side",
        "current_stun", "current_body", "current_end",
        "max_stun", "max_body", "max_end",
        "health", "down",
        "position", "prone", "stunned", "ko", "hidden", "perceives",
    }
