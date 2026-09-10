"""6E2 p.106: a Stunned character cannot Abort to a defensive Action.

`mark_aborting` enforces it and raises. It refuses for TWO reasons ---
already aborted this Phase, and Stunned --- and enumeration gated only
the first. Its own comment, two lines above the gate, describes exactly
what the ungated case does:

    a `ValueError` out of the middle of the turn loop, past
    `on_unresolvable="skip"`, killing the O.K. Corral benchmark the first
    time a man dodged twice.

The same sentence, the same page, the other reason. It killed a
model-driven street fight on the second seed:

    ValueError: combatant 'deputy' is Stunned (or recovering from being
    Stunned) and cannot Abort to a defensive Action (6E2 p.106)

FOUND ONLY BY A MODEL. `TacticChooser` picks `dodge` zero times in 362
Phases, so doctrine can run this scene forever without meeting it. A
benchmark exists to flex the engine, and this is what that looks like.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

import pytest

import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()

#: The enumerable kinds that reach `mark_aborting`, and so the ones the
#: rule has to gate TOGETHER --- gating one and not the other is how this
#: defect survived its first fix.
#:
#: `dive_for_cover` calls `mark_aborting` as well and is deliberately
#: absent: it is neither enumerable nor registered as a resolvable kind,
#: so no chooser can reach it. If it is ever wired, it wears this gate.
DEFENSIVE = ("dodge", "block")


def _menu(*, can_abort: bool):
    session = CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=None,
        combatants=[fighter("hurt", side=Side.named("a")),
                    fighter("foe", side=Side.named("b"))],
    ).start()
    actor = session.combatants["hurt"]
    enemies = [session.combatants["foe"]]
    return enumerate_actions(actor, enemies, can_abort=can_abort)


def test_a_stunned_man_is_offered_no_defensive_abort():
    kinds = {a.kind for a in _menu(can_abort=False)}
    assert not (kinds & set(DEFENSIVE)), sorted(kinds & set(DEFENSIVE))


def test_and_is_still_offered_something():
    """Refusing the defences must not empty the menu --- a Phase with no
    legal action is its own defect, and 6E2 p.106 stops him ABORTING, not
    acting."""
    assert _menu(can_abort=False)


@pytest.mark.parametrize("kind", DEFENSIVE)
def test_a_man_who_can_abort_still_gets_them(kind):
    kinds = {a.kind for a in _menu(can_abort=True)}
    assert kind in kinds, sorted(kinds)


def test_the_driver_asks_the_engine_whether_he_may_abort():
    """`run_phase` computed `already_aborted` and stopped there --- one of
    the two reasons `mark_aborting` refuses. It has to ask the whole
    question or the next reason added will leak the same way."""
    import inspect

    from kirby_combat.loop import run

    source = inspect.getsource(run.run_phase)
    assert "can_abort=" in source, "the driver does not answer the gate"
    assert "stunned_or_recovering_for" in inspect.getsource(run), source[:0]
