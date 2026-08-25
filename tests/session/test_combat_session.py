"""CombatSession construction + initial-state tests."""
from kirby_combat.session import CombatSession, Timeline
from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller


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
