"""Squads and their leaders (squad tactics spec, section 4)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import VitalsChanged, make_author_engine
from kirby_combat.side import Side
from kirby_combat.squads import Squad, leader_of, leader_rule, name_leaders, squads_of
from kirby_combat.synthetic import synthetic_combatant

RED, BLUE = Side.named("red"), Side.named("blue")


def _man(id, *, side=RED, squad="alpha", tactics=None, int_=10, pre=10):
    return synthetic_combatant(
        id=id, name=id, side=side, squad=squad, int_=int_, pre=pre,
        skills={} if tactics is None else {"TACTICS": tactics})


def _fight(*men):
    return CombatSession.create(id="s", combatants=list(men), scene=None,
                                template=None, dice_roller=None).start()


def _knock_out(session, cid):
    stun = session.combatants[cid].state.current_stun
    return apply_event(session, VitalsChanged(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id=cid, stun=-stun, body=0, end=0))


def _namings(session):
    return [e for e in session.event_log if e.kind == "SquadLeaderNamed"]


def _alpha(session):
    (squad,) = [q for q in squads_of(session) if q.name == "alpha"]
    return squad


def test_best_tactics_leads():
    s = _fight(_man("a", tactics=11), _man("b", tactics=13), _man("c"))
    assert leader_rule(s, _alpha(s)) == "b"


def test_a_man_without_tactics_ranks_below_any_roll():
    s = _fight(_man("a", int_=30), _man("b", tactics=8))
    assert leader_rule(s, _alpha(s)) == "b"


def test_int_breaks_a_tactics_tie():
    s = _fight(_man("a", tactics=12, int_=10), _man("b", tactics=12, int_=15))
    assert leader_rule(s, _alpha(s)) == "b"


def test_pre_breaks_an_int_tie():
    s = _fight(_man("a", tactics=12, pre=10), _man("b", tactics=12, pre=15))
    assert leader_rule(s, _alpha(s)) == "b"


def test_seating_order_breaks_the_last_tie():
    s = _fight(_man("a", tactics=12), _man("b", tactics=12))
    assert leader_rule(s, _alpha(s)) == "a"


def test_the_same_name_on_two_sides_is_two_squads():
    s = _fight(_man("a"), _man("b", side=BLUE))
    assert {(q.side, q.member_ids) for q in squads_of(s)} == {
        ("red", ("a",)), ("blue", ("b",))}


def test_leader_down_names_the_next_at_once():
    s = name_leaders(_fight(_man("a", tactics=14), _man("b", tactics=12)))
    assert leader_of(s, "alpha", "red") == "a"
    s = name_leaders(_knock_out(s, "a"))
    assert leader_of(s, "alpha", "red") == "b"
    assert [e.kind for e in s.event_log[-2:]] == ["VitalsChanged", "SquadLeaderNamed"]
    assert s.event_log[-1].reason == "a went down"
    assert [e.reason for e in _namings(s)] == ["fight began", "a went down"]


def test_a_follower_going_down_changes_nothing():
    s = name_leaders(_fight(_man("a", tactics=14), _man("b", tactics=12)))
    s = name_leaders(_knock_out(s, "b"))
    assert len(_namings(s)) == 1


def test_squad_of_one_leads_himself():
    s = name_leaders(_fight(_man("a")))
    assert leader_of(s, "alpha", "red") == "a"


def test_all_down_names_no_one_once():
    s = name_leaders(_fight(_man("a", tactics=14), _man("b", tactics=12)))
    s = name_leaders(_knock_out(_knock_out(s, "a"), "b"))
    assert leader_of(s, "alpha", "red") is None
    s = name_leaders(name_leaders(s))
    assert [e.leader_id for e in _namings(s)] == ["a", None]


def test_no_squad_no_events():
    s = name_leaders(_fight(_man("a", squad=None), _man("b", side=BLUE, squad=None)))
    assert _namings(s) == []
    assert squads_of(s) == ()


def test_an_empty_squad_name_is_refused():
    with pytest.raises(ValueError, match="squad"):
        _man("a", squad="")


def test_the_squad_survives_the_wire_and_a_replace():
    import dataclasses

    from kirby_combat.serialization.from_dict import from_dict
    from kirby_combat.serialization.to_dict import to_dict

    s = _fight(_man("a"))
    assert dataclasses.replace(s.combatants["a"]).squad == "alpha"
    assert to_dict(s.combatants["a"])["squad"] == "alpha"


def test_through_the_loop_the_leader_falls_and_the_next_is_named_in_that_step():
    from conftest import blast  # tests/loop/conftest.py
    from kirby_dice import RandomRoller

    from kirby_combat.encounter import Encounter
    from kirby_combat.loop import run_phase
    from kirby_combat.template import RAW_SUPERHEROIC

    killer = synthetic_combatant(id="k", name="k", ocv=30, spd=4, dex=40, side=BLUE,
                                 attacks=[blast("k-eb", dice=12)])
    lead = _man("l", tactics=14)
    deputy = _man("d", tactics=10)
    session = CombatSession.create(id="s", combatants=[killer, lead, deputy], scene=None,
                                   template=RAW_SUPERHEROIC,
                                   dice_roller=RandomRoller(seed=3)).start()

    class _Shoot:
        def choose(self, situation):
            for x in situation.menu:
                if x.kind == "no_abort":
                    return x.action_id
            return next(x.action_id for x in situation.menu
                        if x.kind == "attack" and x.target_id == "l")

    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    r = RandomRoller(seed=3)
    phase = run_phase(enc.run_segment(roller=lambda: r.roll_dice(3)), _Shoot(),
                      roller=RandomRoller(seed=3), on_unresolvable="raise")
    s = phase.session
    kinds = [(e.kind, getattr(e, "combatant_id", None)) for e in s.event_log]
    assert [e.reason for e in _namings(s)] == ["fight began", "l went down"], kinds
    assert leader_of(s, "alpha", "red") == "d"
    ko = max(i for i, e in enumerate(s.event_log)
             if e.kind == "VitalsChanged" and e.combatant_id == "l")
    assert s.event_log[ko + 1].kind == "SquadLeaderNamed" or any(
        e.kind == "SquadLeaderNamed" and e.reason == "l went down"
        for e in s.event_log[ko + 1:ko + 6])
    assert [e.kind for e in phase.events].count("SquadLeaderNamed") == 2
