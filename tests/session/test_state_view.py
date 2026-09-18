"""The readable projection of a rewound session — the engine's own readings.

A viewer folds the event log for display and must be checkable against the
engine's fold. This is the shape it is checked against, and every value on
it is read through the engine's own function: `classify_health` for the
rung, `is_down` for whether he is still in it, `Side.of` for whose part he
is on. A second reading here would be the thing the check exists to catch.
"""
from __future__ import annotations

import dataclasses

import pytest

from kirby_combat import state_view
from kirby_combat.health import classify_health
from kirby_combat.enumeration import is_down
from kirby_combat.side import Side

from tests.combat_fixtures import (
    a_fight_that_has_happened, a_roller, an_invisible_fighter_session,
    flashed_session, placed_session, two_fighter_session,
)


def test_the_view_reads_the_clock_and_the_status_off_the_session():
    session = two_fighter_session()

    view = state_view(session, roller=a_roller())

    assert view.status == session.status
    assert view.turn == session.timeline.turn
    assert view.segment == session.timeline.segment


def test_last_sequence_is_the_last_event_not_the_log_length():
    """A log holding only `SessionStarted` is a fight nothing has happened
    in, and answers 0 — as does a session still in setup, whose log is
    empty. Read off the last event rather than counted from the length."""
    session = two_fighter_session()

    assert state_view(session, roller=a_roller()).last_sequence == 0
    assert state_view(session.start(), roller=a_roller()).last_sequence == 0
    assert state_view(a_fight_that_has_happened(), roller=a_roller()).last_sequence == (
        a_fight_that_has_happened().event_log[-1].sequence
    )


def test_every_combatant_is_projected_through_the_engines_own_readings():
    session = two_fighter_session()

    view = state_view(session, roller=a_roller())

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


def test_spd_and_dex_are_build_facts_read_through_combat_stats():
    """Krackle's SPD ribbon and DEX ordering need these, and they are
    bought on the sheet rather than folded from the log — like
    `max_stun`/`max_body`/`max_end`, read through `combat_stats()`, the
    one door every characteristic goes through, never re-derived here."""
    session = two_fighter_session()

    view = state_view(session, roller=a_roller())

    assert len(view.combatants) == len(session.combatants)
    for c in view.combatants:
        live = session.combatants[c.id]
        stats = live.combat_stats()
        assert c.spd == stats.spd
        assert c.dex == stats.dex


def test_the_view_carries_where_he_is_and_which_way_he_faces():
    """`position_of` is the door. A combatant not on the map reads None —
    NOT the origin, which would put him adjacent to whoever stands at
    (0, 0, 0) in every distance a consumer computes off this."""
    session = placed_session()

    view = state_view(session, roller=a_roller())

    alice = next(c for c in view.combatants if c.id == "alice")
    assert (alice.position.x, alice.position.y, alice.position.z) == (0.0, 0.0, 0.0)
    assert alice.position.facing == 0.0

    assert next(
        c for c in state_view(two_fighter_session(), roller=a_roller()).combatants
    ).position is None


def test_the_conditions_come_from_the_one_status_door():
    """`statuses_for` folds every condition source out of the log — Prone
    from a Trip's payload, Stunned from a resolution, Knocked Out from
    both a payload and the vitals. Reading any one of those sources here
    instead would be a second fold of the same fact."""
    from kirby_combat.statuses import KNOCKED_OUT, PRONE, STUNNED, statuses_for

    session = a_fight_that_has_happened()

    for c in state_view(session, roller=a_roller()).combatants:
        held = statuses_for(session, c.id)
        assert c.prone == (PRONE in held)
        assert c.stunned == (STUNNED in held)
        assert c.ko == (KNOCKED_OUT in held)


def test_the_next_actor_is_a_question_and_spends_no_slot():
    from kirby_combat import next_actor_id

    session = a_fight_that_has_happened()

    before = [s.has_acted for s in session.timeline.acting_order]
    view = state_view(session, roller=a_roller())

    assert view.next_actor_id == next_actor_id(session)
    assert [s.has_acted for s in session.timeline.acting_order] == before


def test_a_man_nobody_can_see_is_absent_from_the_observers_perceives():
    """THE PERCEPTION CASE, and the reason fog stops failing open.

    A viewer used to filter the board from a per-segment audit row the
    consuming service wrote, and with no row the fog failed OPEN — the
    view showed EVERYONE while claiming to show one man's eyes. The
    engine already owns this answer: `concealment.perceives` is the one
    door that hands the log's concealment and the build's Invisibility to
    `perception.perceive` together — with the observer's own Flash — so a
    caller cannot forget one of them. This surfaces it; it decides
    nothing.

    Flash is the clean lever because it needs no geometry: a fighter
    Flashed in the Sight Group perceives nobody, and everyone still
    perceives him.
    """
    session = flashed_session()

    view = state_view(session, roller=a_roller())

    blinded = next(c for c in view.combatants if c.id == "alice")
    other = next(c for c in view.combatants if c.id == "bob")
    assert blinded.perceives == []
    assert "alice" in other.perceives


def test_an_invisible_man_is_in_nobodys_perceives_and_still_sees_everyone():
    """THE INVISIBILITY CASE, and the reason the door is the door.

    `sense_penalties.cannot_perceive` reaches `perceive` without the
    concealment arguments, so Invisibility is not partly folded there —
    it is skipped entirely, and a view built on it would publish an
    Invisible man as seen by every enemy on the board while claiming to
    be the engine's answer. `concealment.perceives` is the one place the
    build's Invisibility and the log's hiding are handed over together.

    Ten metres apart, so nobody is inside the 2 m Fringe and no PER roll
    is drawn. The engine does NOT make Invisibility side-aware: an ally
    is as blind to it as an enemy, and this pins that rather than
    inventing an exemption the rule does not have."""
    view = state_view(an_invisible_fighter_session(), roller=a_roller())

    alice = next(c for c in view.combatants if c.id == "alice")
    enemy = next(c for c in view.combatants if c.id == "bob")
    ally = next(c for c in view.combatants if c.id == "carol")

    assert alice.invisible is True
    assert "alice" not in enemy.perceives
    assert "alice" not in ally.perceives
    # He is invisible, not blind.
    assert alice.perceives == ["bob", "carol"]
    # And nobody else's build carries it.
    assert enemy.invisible is False and ally.invisible is False


def test_unseen_ness_is_published_per_observer_and_never_flattened():
    """`perceives` is the ONLY place being unseen is reported, and it is
    per observer — which is the granularity the engine's own Hide
    contest resolves at, "because being unseen is not a property of the
    hider: one enemy may lose you while another keeps you in view". A
    flat `hidden` beside it would answer the same question at a second
    granularity, and a consumer could not recover the pairwise truth."""
    fields = {
        f.name for f in dataclasses.fields(
            state_view(two_fighter_session(), roller=a_roller()).combatants[0])
    }

    assert "hidden" not in fields
    assert "unseen_by" not in fields
    assert "perceives" in fields


def test_the_view_takes_its_roller_and_never_makes_one():
    """THE PLAYBACK PROPERTY. `state?at=N` serialises this view, and two
    reads of sequence N must agree or a replay is not a replay.

    `perceive` builds its own `RandomRoller` when handed none, so a view
    that did not demand one would answer differently every call for the
    two rolled pair kinds. There is no default: a caller that has not
    thought about it gets a TypeError, not a silent reseed."""
    session = an_invisible_fighter_session(close_enough_for_the_fringe=True)

    with pytest.raises(TypeError):
        state_view(session)          # no roller — refused, not guessed

    first = state_view(session, roller=a_roller(11))
    again = state_view(session, roller=a_roller(11))

    assert first == again


def test_only_the_two_rolled_pair_kinds_may_differ_between_seeds():
    """The other half: everything that is a READ is the same whatever
    roller is handed in, and the only thing a seed can move is whether an
    Invisible man inside the 2 m Fringe was spotted.

    Bob stands 1 m from the Invisible alice, so his pair is the PER roll.
    Carol stands ten metres away, beyond the Fringe, so hers is a read
    and must never move. The last two assertions are the negative
    control: the rolled pair really does go both ways across seeds, so
    this test is not passing because nothing ever rolls."""
    session = an_invisible_fighter_session(close_enough_for_the_fringe=True)

    def without_the_rolled_pair(view):
        return [
            dataclasses.replace(
                c, perceives=[p for p in c.perceives if p != "alice"])
            for c in view.combatants
        ]

    views = [state_view(session, roller=a_roller(seed)) for seed in range(12)]

    for view in views:
        assert without_the_rolled_pair(view) == without_the_rolled_pair(views[0])
        carol = next(c for c in view.combatants if c.id == "carol")
        assert "alice" not in carol.perceives

    spotted = {
        "alice" in next(c for c in v.combatants if c.id == "bob").perceives
        for v in views
    }
    assert spotted == {True, False}


def test_nobody_perceives_himself():
    """`perceives` is who ELSE he can see. Including himself would make
    every consumer subtract him again."""
    for c in state_view(two_fighter_session(), roller=a_roller()).combatants:
        assert c.id not in c.perceives


def test_the_view_is_frozen_and_flat():
    """Nothing on it is a live engine object: a viewer serialises it."""
    view = state_view(two_fighter_session(), roller=a_roller())
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
        "spd", "dex",
        "health", "down",
        "position", "prone", "stunned", "ko", "invisible", "perceives",
    }
