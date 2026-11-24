"""The end of a fight (two-databases spec §6a; plan 2026-11-24-fight-end).

A fight ends only through one engine event, `SessionEnded`, in its log:
typed (`Ending`), with the winning side, authored by whoever confirmed it.
How it gets there is the fight's own TERMS, stated once as it starts
(`FightTermsStated`, like `RulingsStated`): which stop condition decides it,
and whether the engine ends it on its own (`AUTO_STOP`) or asks the GM
(`ASK`). Peter, 2026-11-24: "we can ask the gm if thats the end", "or
auto-stop", "allow a choice".

Before this, `SessionEnded` existed and nothing emitted it: no fight's log
recorded its end, so a replay could not show it and a campaign had nothing
to carry consequences back on.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from conftest import encounter_of, fighter
from kirby_combat.ending import (
    EndMode, Ending, FightTerms, FightTermsMissing, StopKind, answer_end,
    call_fight, ended, state_terms, terms_of,
)
from kirby_combat.encounter import Encounter
from kirby_combat.loop import FirstLegalChooser, Roster, run_phase
from kirby_combat.session.rewind import rewind_to_sequence
from kirby_combat.side import Side
from kirby_dice import RandomRoller

X, Y = Side.named("x"), Side.named("y")
GM = "gm-1"


def _swap(enc: Encounter, session) -> Encounter:
    return replace(enc, sessions=[session])


def _bare(*fighters) -> Encounter:
    """An encounter whose fight has NO terms yet."""
    enc = encounter_of(*fighters)
    session = enc.sessions[0]
    return _swap(enc, replace(session, event_log=[
        e for e in session.event_log if e.kind != "FightTermsStated"]))


def _with_terms(enc: Encounter, stop: StopKind, mode: EndMode) -> Encounter:
    session = enc.sessions[0]
    bare = replace(session, event_log=[
        e for e in session.event_log if e.kind != "FightTermsStated"])
    return _swap(enc, state_terms(bare, FightTerms(stop=stop, end_mode=mode)))


def _decided(mode: EndMode) -> Encounter:
    """x standing, y already down: last side standing says x has won."""
    return _with_terms(
        encounter_of(fighter("a", side=X), fighter("b", side=Y, stun=0)),
        StopKind.LAST_SIDE_STANDING, mode)


def _open(mode: EndMode, stop: StopKind = StopKind.LAST_SIDE_STANDING) -> Encounter:
    return _with_terms(
        encounter_of(fighter("a", side=X, dex=25), fighter("b", side=Y)),
        stop, mode)


def _step(enc: Encounter):
    return run_phase(enc, FirstLegalChooser(), roller=RandomRoller(seed=3),
                     on_unresolvable="skip")


def _kinds(session) -> list[str]:
    return [e.kind for e in session.event_log]


# ---- terms ---------------------------------------------------------------

def test_a_fight_with_no_terms_refuses_to_step():
    enc = _bare(fighter("a", side=X), fighter("b", side=Y))
    with pytest.raises(FightTermsMissing):
        _step(enc)


def test_terms_are_read_back_from_the_log():
    enc = _open(EndMode.ASK)
    assert terms_of(enc.sessions[0]) == FightTerms(
        stop=StopKind.LAST_SIDE_STANDING, end_mode=EndMode.ASK)


def test_terms_are_stated_once():
    enc = _open(EndMode.ASK)
    with pytest.raises(ValueError, match="already stated"):
        state_terms(enc.sessions[0], FightTerms(
            stop=StopKind.FIRST_BLOOD, end_mode=EndMode.AUTO_STOP))


def test_terms_cannot_change_once_the_fight_has_moved():
    moved = _step(_open(EndMode.AUTO_STOP)).encounter
    session = moved.sessions[0]
    # Strip the terms row to prove the WINDOW refuses, not the once-rule.
    bare = replace(session, event_log=[e for e in session.event_log
                                       if e.kind != "FightTermsStated"])
    with pytest.raises(ValueError, match="fixed when the fight starts"):
        state_terms(bare, FightTerms(stop=StopKind.GM_ONLY,
                                     end_mode=EndMode.ASK))


# ---- auto-stop -----------------------------------------------------------

def test_auto_stop_ends_a_decided_fight_in_the_log():
    out = _step(_decided(EndMode.AUTO_STOP))
    end = ended(out.session)
    assert end is not None
    assert end.ending == Ending.DECIDED
    assert end.winner == X.id
    assert end.author.type == "engine"
    assert out.kind == "ended" and out.actor_id is None
    assert out.session.status == "ended"
    assert [e.kind for e in out.events] == ["SessionEnded"]


def test_an_ended_fight_writes_nothing_more():
    first = _step(_decided(EndMode.AUTO_STOP))
    again = _step(first.encounter)
    assert again.events == [] and again.kind == "ended"
    assert _kinds(again.session) == _kinds(first.session)


# ---- ask -----------------------------------------------------------------

def test_ask_proposes_the_end_instead_of_ending():
    out = _step(_decided(EndMode.ASK))
    assert ended(out.session) is None
    assert out.kind == "end_question" and out.actor_id is None
    proposed = out.events[-1]
    assert proposed.kind == "EndProposed"
    assert proposed.ending == Ending.DECIDED and proposed.winner == X.id


def test_an_open_question_holds_the_fight_still():
    asked = _step(_decided(EndMode.ASK))
    again = _step(asked.encounter)
    assert again.events == [] and again.kind == "end_question"


def test_the_gm_saying_yes_ends_it_as_the_gm():
    asked = _step(_decided(EndMode.ASK))
    done = answer_end(asked.session, accept=True, gm_id=GM)
    end = ended(done)
    assert end.ending == Ending.DECIDED and end.winner == X.id
    assert end.author.type == "gm" and end.author.id == GM


def test_the_gm_saying_no_carries_on_without_asking_again():
    asked = _step(_decided(EndMode.ASK))
    declined = answer_end(asked.session, accept=False, gm_id=GM)
    assert declined.event_log[-1].kind == "EndDeclined"
    enc = _swap(asked.encounter, declined)
    nxt = _step(enc)
    assert nxt.kind != "end_question", "a declined verdict is not asked again"
    assert ended(nxt.session) is None


def test_answering_with_no_question_open_is_refused():
    enc = _open(EndMode.ASK)
    with pytest.raises(ValueError, match="no end has been proposed"):
        answer_end(enc.sessions[0], accept=True, gm_id=GM)


# ---- calling a fight -----------------------------------------------------

@pytest.mark.parametrize("mode", [EndMode.ASK, EndMode.AUTO_STOP])
def test_the_gm_can_call_a_fight_at_any_time(mode):
    done = call_fight(_open(mode).sessions[0], gm_id=GM)
    end = ended(done)
    assert end.ending == Ending.CALLED and end.winner is None
    assert end.author.type == "gm"


def test_calling_a_fight_closes_an_open_question():
    asked = _step(_decided(EndMode.ASK))
    done = call_fight(asked.session, gm_id=GM)
    assert ended(done).ending == Ending.CALLED
    with pytest.raises(ValueError, match="already ended"):
        answer_end(done, accept=True, gm_id=GM)


def test_a_fight_ends_once():
    done = call_fight(_open(EndMode.ASK).sessions[0], gm_id=GM)
    with pytest.raises(ValueError, match="already ended"):
        call_fight(done, gm_id=GM)


# ---- stop kinds ----------------------------------------------------------

def test_gm_only_never_ends_on_its_own():
    out = _step(_with_terms(
        encounter_of(fighter("a", side=X), fighter("b", side=Y, stun=0)),
        StopKind.GM_ONLY, EndMode.AUTO_STOP))
    assert ended(out.session) is None and out.kind != "end_question"


def test_first_blood_is_won_by_the_side_nobody_hurt():
    hurt = encounter_of(fighter("a", side=X), fighter("b", side=Y, stun=30))
    out = _step(_with_terms(hurt, StopKind.FIRST_BLOOD, EndMode.AUTO_STOP))
    assert ended(out.session).winner == X.id


def test_roster_decide_names_its_condition():
    session = encounter_of(fighter("a", side=X), fighter("b", side=Y)).sessions[0]
    with pytest.raises(TypeError):
        Roster(session).decide()


# ---- replay --------------------------------------------------------------

def test_the_end_survives_the_replay():
    """A fight folded back from its own log ends the same way."""
    asked = _step(_decided(EndMode.ASK))
    done = answer_end(asked.session, accept=True, gm_id=GM)
    rebuilt = rewind_to_sequence(done, len(done.event_log) - 1)
    from kirby_combat.session.apply import apply_event
    rebuilt = apply_event(rebuilt, done.event_log[-1])
    assert rebuilt.status == "ended"
    assert ended(rebuilt) == ended(done)
    assert terms_of(rebuilt) == terms_of(done)
