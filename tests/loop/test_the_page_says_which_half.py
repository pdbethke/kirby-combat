"""The seat is told how much of the Phase is left (6E2 p.20).

Since the Half Phase economy (#24) a Phase can come back to the same man
after a Half Phase Action, and the menu is cut to what fits in the second
half (`action_time.rest_of_phase`). The SEAT was not told: a model, a
player's standing orders and a person at the table all saw a shorter menu
with nothing saying why. `PhaseSituation.halves_left` says it, read from
`action_time` (one source, nothing stored), and the Brief says it in words.

* his own Phase: 2 at the start, 1 after a first Half Phase Action
  (1 all along for a very impressed man, 6E2 p.139);
* a Held Action question: 1 when he Held only the second half (6E2 p.22),
  else 2;
* an Abort question: None. An Abort is not taken out of a Phase in hand;
  it costs his NEXT Phase (6E2 p.24).
"""
from __future__ import annotations

from conftest import blast                                    # tests/loop/conftest.py
from shaped import Dice, armed, encounter_on, scene_with      # tests/loop/shaped.py
from kirby_combat.loop import run_phase
from kirby_combat.loop.chooser import OutOfTurnReason
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


def _two_men(distance):
    scene = scene_with({"a": (0, 0, 0), "b": (distance, 0, 0)})
    return encounter_on(scene, armed("a", blast("a-eb", 4), side=VILLAINS, dex=30),
                        armed("b", None, side=HEROES, dex=10))


class Seen:
    """Takes each wanted kind in turn on his own Phase; declines out of turn.
    Keeps (actor, reason, halves_left, page) for every question."""

    def __init__(self, *wants):
        self.wants = list(wants)
        self.seen = []

    def choose(self, situation):
        oot = situation.out_of_turn
        self.seen.append((situation.actor.id, oot.reason if oot else None,
                          situation.halves_left, situation.brief().render()))
        if oot is not None or not self.wants:
            return situation.menu[0].action_id
        want = self.wants.pop(0)
        return next(a.action_id for a in situation.menu if a.kind == want)


def test_his_own_phase_says_two_halves_then_one():
    chooser = Seen("half_move", "attack")
    first = run_phase(_two_men(30.0), chooser, roller=Dice(face=3), on_unresolvable="raise")
    run_phase(first.encounter, chooser, roller=Dice(face=3), on_unresolvable="raise")
    own = [(h, page) for who, reason, h, page in chooser.seen if who == "a" and reason is None]
    assert [h for h, _ in own] == [2, 1]
    assert "second half of your Phase" not in own[0][1]
    assert "second half of your Phase" in own[1][1]


def test_an_abort_question_is_not_taken_out_of_a_phase():
    """b is asked whether he Aborts against a's attack: no halves to count."""
    chooser = Seen("attack")
    run_phase(_two_men(8.0), chooser, roller=Dice(face=3), on_unresolvable="raise")
    abort = [h for who, reason, h, _ in chooser.seen if reason is OutOfTurnReason.ABORT]
    assert abort == [None]


def test_a_held_half_says_one_half():
    """6E2 p.22: a Half Phase Action, then Hold the other half."""
    chooser = Seen("half_move", "hold")
    first = run_phase(_two_men(30.0), chooser, roller=Dice(face=3), on_unresolvable="raise")
    second = run_phase(first.encounter, chooser, roller=Dice(face=3), on_unresolvable="raise")
    assert second.kind == "hold"
    asked = Seen()
    run_phase(second.encounter, asked, roller=Dice(face=3), on_unresolvable="raise")
    held = [(h, page) for who, reason, h, page in asked.seen
            if who == "a" and reason is OutOfTurnReason.HELD_ACTION]
    assert held and held[0][0] == 1
    assert "Half Phase" in held[0][1]


def test_a_whole_held_phase_says_two():
    chooser = Seen("hold")
    first = run_phase(_two_men(30.0), chooser, roller=Dice(face=3), on_unresolvable="raise")
    asked = Seen()
    run_phase(first.encounter, asked, roller=Dice(face=3), on_unresolvable="raise")
    held = [h for who, reason, h, _ in asked.seen
            if who == "a" and reason is OutOfTurnReason.HELD_ACTION]
    assert held == [2]


def test_a_situation_with_no_fight_cannot_say():
    import pytest
    from kirby_combat.loop.chooser import PhaseSituation

    with pytest.raises(ValueError):
        PhaseSituation(actor=armed("a", None), menu=[]).halves_left
