"""The Earps leave the lot.

The acceptance test the morale spec named: Power Lad kills Virgil and
Wyatt in the first two Turns, and a side that has lost half its men to
something its bullets bounce off should not still be standing there at
Turn 3. Success is not that they lose --- they lose now. It is that the
survivors GO, and that whoever cannot conceive of losing is the last man
shooting.
"""
from __future__ import annotations

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.side import Side
from kirby_combat.tactics.base import Situation
from kirby_combat.tactics.library import all_tactics


class _Session:
    def __init__(self, combatants):
        self.combatants = {c.id: c for c in combatants}
        self.event_log = []


def _man(id_, *, side="law", down=False, proud=False):
    c = fighter(id_, side=Side.named(side), armed=True,
                stun=0 if down else 40)
    if proud:
        c.hero.complications = [_Proud()]
    return c


class _Proud:
    xmlid = "PSYCHOLOGICALLIMITATION"
    input = "Overconfidence"
    alias = "Psychological Complication"
    adder_string = ""
    adders: list = []
    name = ""


def _tactic():
    return next(t for t in all_tactics() if t.name == "leave_when_the_side_has_broken")


def _situation(actor, side_members, *, enemies=None):
    session = _Session(side_members + (enemies or []))
    return Situation(
        actor=actor, allies=[m for m in side_members if m is not actor],
        enemies=enemies or [_man("monster", side="solo")],
        current_segment=12, turn=1, session=session)


def test_a_side_that_has_lost_half_its_men_leaves():
    """The Earps at Turn 2 --- Virgil and Wyatt gone of four."""
    survivors = [_man("morgan"), _man("doc")]
    side = [_man("virgil", down=True), _man("wyatt", down=True)] + survivors
    situation = _situation(survivors[0], side)
    assert _tactic().applicable(situation)
    assert _tactic().execute(situation).steps[0].kind == "disengage"


def test_a_side_that_has_lost_one_man_stays():
    """Men die in fights. One is not a rout, and a doctrine that treated
    it as one would empty every fight in the corpus."""
    survivors = [_man("morgan"), _man("doc"), _man("wyatt")]
    side = [_man("virgil", down=True)] + survivors
    assert not _tactic().applicable(_situation(survivors[0], side))


def test_the_overconfident_man_is_the_last_one_shooting():
    """PeterB's half of the design. The side breaks; he does not, because
    he cannot conceive of losing."""
    proud = _man("frank", proud=True)
    side = [_man("tom", down=True), _man("billy", down=True), proud,
            _man("ike")]
    assert not _tactic().applicable(_situation(proud, side))
    assert _tactic().applicable(_situation(side[-1], side))


def test_the_dead_count_toward_the_side_that_lost_them():
    """A side of four that has lost two is not a side of two that has lost
    nobody, and reading only the survivors would say exactly that. They
    come off the SESSION, since `allies` holds only who is still up."""
    survivors = [_man("morgan"), _man("doc")]
    side = [_man("virgil", down=True), _man("wyatt", down=True)] + survivors
    situation = _situation(survivors[0], side)
    assert len(situation.allies) == 3, "allies is the living side plus the dead here"
    assert _tactic().applicable(situation)


def test_no_session_means_no_opinion():
    """Most callers drive without one, and a tactic that cannot see the
    side must not guess that it has broken."""
    actor = _man("morgan")
    situation = Situation(actor=actor, allies=[], enemies=[_man("m", side="solo")],
                          current_segment=12, turn=1)
    assert not _tactic().applicable(situation)
