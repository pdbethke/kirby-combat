"""CombatSession construction + initial-state tests."""
from datetime import datetime, timezone

from kirby_combat.session import CombatSession, Timeline
from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.template import CombatTemplate
from kirby_dice import FakeRoller


def _mk_c(id_: str, spd: int, dex: int) -> "HeroCombatant":
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=spd, dex=dex, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def test_create_session_minimum_fields():
    s = CombatSession.create(
        id="s1",
        combatants=[_mk_c("alice", spd=4, dex=20), _mk_c("bob", spd=3, dex=15)],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    )
    assert s.id == "s1"
    assert set(s.combatants.keys()) == {"alice", "bob"}
    assert s.status == "setup"
    assert s.timeline.turn == 1
    assert s.timeline.segment == 12
    assert s.event_log == []


def test_session_start_emits_sessionstarted_event_and_advances_status():
    s = CombatSession.create(
        id="s1",
        combatants=[_mk_c("alice", spd=4, dex=20)],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    )
    s = s.start()
    assert s.status == "active"
    assert len(s.event_log) == 1
    assert s.event_log[0].kind == "SessionStarted"


def test_session_pause_and_resume():
    s = CombatSession.create(
        id="s1", combatants=[_mk_c("alice", 4, 20)],
        scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()
    s = s.pause()
    assert s.status == "paused"
    s = s.resume()
    assert s.status == "active"


def test_session_end_is_terminal():
    s = CombatSession.create(
        id="s1", combatants=[_mk_c("alice", 4, 20)],
        scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start().end(reason="tpk")
    assert s.status == "ended"
    s2 = s.end(reason="double-end")
    assert s2.status == "ended"
    ends = [e for e in s2.event_log if e.kind == "SessionEnded"]
    assert len(ends) == 1


# ---------------------------------------------------------------------------
# The men as the fight found them
# ---------------------------------------------------------------------------

def _a_man(id: str = "a", *, stun: int = 40):
    return synthetic_combatant(
        id=id, name=id, spd=4, dex=20, rec=6,
        max_stun=40, max_body=12, max_end=40,
        current_stun=stun, current_body=12, current_end=40,
    )


def test_an_empty_log_may_infer_the_starting_combatants():
    """A session with no events has not been in a fight: the men it holds
    ARE the men it started with, and that is not a guess."""
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate

    session = CombatSession(
        id="s", combatants={"a": _a_man()}, scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        timeline=Timeline(turn=1, segment=12, acting_order=[],
                          current_slot_index=0),
    )

    assert set(session.initial_combatants) == {"a"}


def test_a_mid_fight_construction_refuses_to_infer_them():
    """THE SILENT WRONG ANSWER, refused. `initial_combatants` is what
    `rewind_to_sequence` replays INTO; inferring it from a session that
    already has events means inferring the start from the men the fight
    LEFT, and every later rewind then replays the fight's damage on top of
    itself and returns a session more hurt than the fight ever got --- with
    nothing saying so.
    """
    import pytest

    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.session.events import SessionStarted, make_author_engine
    from kirby_combat.template import CombatTemplate

    started = SessionStarted(
        id="e1", session_id="s", sequence=1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        scene_id="", combatant_ids=["a"],
    )

    with pytest.raises(ValueError, match="initial_combatants"):
        CombatSession(
            id="s", combatants={"a": _a_man(stun=12)}, scene=None,
            template=CombatTemplate.default_6e_superheroic(),
            timeline=Timeline(turn=1, segment=12, acting_order=[],
                              current_slot_index=0),
            event_log=[started],
        )


def test_a_mid_fight_construction_that_is_told_the_start_is_fine():
    """The way out is to say what the fight started from, not to guess."""
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.session.events import SessionStarted, make_author_engine
    from kirby_combat.template import CombatTemplate

    started = SessionStarted(
        id="e1", session_id="s", sequence=1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        scene_id="", combatant_ids=["a"],
    )

    session = CombatSession(
        id="s", combatants={"a": _a_man(stun=12)}, scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        timeline=Timeline(turn=1, segment=12, acting_order=[],
                          current_slot_index=0),
        event_log=[started],
        initial_combatants={"a": _a_man(stun=40)},
    )

    assert session.initial_combatants["a"].state.current_stun == 40
    assert session.combatants["a"].state.current_stun == 12
