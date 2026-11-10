"""The engine rolls his read of the fight once a Phase (6E1 p.93).

A seat used to roll it itself (kirby-ai's notice roll and Set check), on the
session's dice and outside the log. The loop rolls it now, records
`FightRead`, and every seat reads `PhaseSituation.fight_read`.
"""
from __future__ import annotations

from types import SimpleNamespace

from conftest import fighter                             # tests/loop/conftest.py
from kirby_dice import FakeRoller, RandomRoller

from kirby_combat.fight_reading import fight_read, read_the_fight, reading_roll
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _session(*cast):
    return CombatSession.create(id="s", combatants=list(cast), scene=None,
                                template=TEMPLATE, dice_roller=RandomRoller(seed=1)).start()


def _pair():
    return _session(fighter("a", side=Side.named("x")), fighter("b", side=Side.named("y")))


def test_without_tactics_he_reads_it_on_int():
    skill, target = reading_roll(fighter("a"))
    assert skill == "INT" and target > 0


def test_with_tactics_he_reads_it_on_tactics():
    man = fighter("a")
    man.skill_roll_value = lambda x: 13 if x == "TACTICS" else None
    assert reading_roll(man) == ("TACTICS", 13)


def test_rolled_once_a_phase_and_recorded():
    s = read_the_fight(_pair(), "a", FakeRoller([[2, 2, 2]]))
    s = read_the_fight(s, "a", FakeRoller([]))          # no second roll owed
    reads = [e for e in s.event_log if e.kind == "FightRead"]
    assert len(reads) == 1 and reads[0].roll == 6 and reads[0].made
    assert fight_read(s, "a") is reads[0]


def test_the_situation_shows_it_on_his_phase_only():
    from kirby_combat.loop.chooser import PhaseSituation

    s = read_the_fight(_pair(), "a", FakeRoller([[6, 6, 6]]))
    own = PhaseSituation(actor=s.combatants["a"], menu=[], session=s)
    assert own.fight_read is not None and not own.fight_read.made
    out = PhaseSituation(actor=s.combatants["a"], menu=[], session=s,
                         out_of_turn=SimpleNamespace(reason=None))
    assert out.fight_read is None
