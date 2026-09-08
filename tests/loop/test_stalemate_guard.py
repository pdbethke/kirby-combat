"""A fight that is going nowhere should stop going nowhere.

`max_turns` is a guard on LENGTH and the only one there was, so a fight
that had stopped progressing still ran to the end of it. The O.K. Corral
with Power Lad in it did exactly that three separate ways in one
afternoon --- 152 reallocations the engine refused, then 152 it accepted
that changed nothing, then 265 Sets --- each one 289 Phases of nobody
being touched.

Every one of those was a real defect worth fixing on its own, and fixing
them one at a time is chasing symptoms: the loop had no notion that a
fight can be ALIVE and going nowhere. This is that notion.

PROGRESS IS SOMETHING HAPPENING TO SOMEBODY. Damage, movement, a status
landing, a Presence effect. Not "an action resolved" --- Setting your aim
for the two hundredth time resolves perfectly well.

It ends the fight UNDECIDED, which is honest: nobody won. A stalemate
reported as a stalemate is a result a caller can act on, and 289 Phases
of silence is not.
"""
from __future__ import annotations

from conftest import encounter_of, fighter        # tests/loop/conftest.py
from kirby_combat.loop import run_encounter
from kirby_combat.loop.chooser import PhaseSituation
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


class _AlwaysSets:
    """A chooser that aims for ever and never fires --- which is what the
    benchmark's last two survivors actually did."""

    name = "always-sets"

    def choose(self, situation: PhaseSituation) -> str:
        for action in situation.menu:
            if action.kind == "set":
                return action.action_id
        return situation.menu[0].action_id


def _fight(**kw):
    encounter = encounter_of(
        fighter("a", side=Side.named("x")), fighter("b", side=Side.named("y")),
    )
    return run_encounter(encounter, _AlwaysSets(), roller=RandomRoller(seed=3),
                         on_unresolvable="skip", max_turns=40, **kw)


def test_a_fight_where_nothing_happens_stops_early():
    """Not at the 40-Turn guard --- long before it."""
    result = _fight()
    assert result.phases < 60, (
        f"ran {result.phases} Phases with nothing happening to anybody"
    )


def test_it_reports_a_stalemate_rather_than_a_winner():
    result = _fight()
    assert result.complete is False
    assert result.winner is None


def test_it_says_why():
    """A caller reading `notes` must be able to tell a stalemate from
    having simply run out of Turns."""
    result = _fight()
    assert any("nothing" in n.lower() or "stalemate" in n.lower()
               for n in result.notes), result.notes


def test_an_ordinary_fight_is_not_cut_short():
    """The guard that matters most: a real fight must reach its own end.
    Two men actually shooting each other resolve normally."""
    from kirby_combat.loop import FirstLegalChooser

    encounter = encounter_of(
        fighter("a", side=Side.named("x")), fighter("b", side=Side.named("y")),
    )
    result = run_encounter(encounter, FirstLegalChooser(),
                           roller=RandomRoller(seed=3),
                           on_unresolvable="skip", max_turns=40)
    assert result.complete, result.notes
