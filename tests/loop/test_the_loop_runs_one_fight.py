"""The loop steps ONE fight, and says so rather than losing the rest.

THE DEFECT THIS PINS. `Encounter` can hold several sessions --- several
fights sharing one clock, which `run_segment` interleaves into one scene-
wide DEX order --- but the loop was written for one. It read
`sessions[0]` throughout and put the result back with
`sessions=[session]`, so an Encounter holding two fights came out of
`run_phase` holding one. The second fight was not paused or skipped; it
was deleted, and nothing said so.

Stepping several fights by Phase needs decisions the loop does not make
(whose Phase is next across fights, when "the fight" is over), so until
those are made it refuses an Encounter it cannot step whole.
"""
from __future__ import annotations

import pytest
from dataclasses import replace

from conftest import fighter, session_of  # tests/loop/conftest.py

from kirby_combat.encounter import Encounter
from kirby_combat.loop import FirstLegalChooser, run_encounter, run_phase
from kirby_combat.side import Side
from kirby_dice import RandomRoller


def _two_fights() -> Encounter:
    first = session_of(
        fighter("a", side=Side.named("blue")),
        fighter("b", side=Side.named("red")),
    )
    second = session_of(
        fighter("c", side=Side.named("blue")),
        fighter("d", side=Side.named("red")),
    )
    second = replace(second, id="s2")
    return Encounter(id="e", turn=1, segment=12, sessions=[first, second])


def test_run_phase_refuses_rather_than_dropping_a_fight():
    with pytest.raises(ValueError, match="one session"):
        run_phase(_two_fights(), FirstLegalChooser(),
                  roller=RandomRoller(seed=1))


def test_run_encounter_refuses_rather_than_dropping_a_fight():
    with pytest.raises(ValueError, match="one session"):
        run_encounter(_two_fights(), FirstLegalChooser(),
                      roller=RandomRoller(seed=1))


def test_one_fight_still_runs():
    encounter = Encounter(id="e", turn=1, segment=12, sessions=[session_of(
        fighter("a", side=Side.named("blue")),
        fighter("b", side=Side.named("red")),
    )])
    phase = run_phase(encounter, FirstLegalChooser(),
                      roller=RandomRoller(seed=1))
    assert len(phase.encounter.sessions) == 1
