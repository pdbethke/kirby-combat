"""`recover` was registered, offered, and could not execute.

    TypeError: apply_event() takes 2 positional arguments but 3 were given

`_resolve_recover` passes `(before, session, RecoveryTaken(...))` to an
`apply_event(session, event)` --- a stray argument that made the resolver
raise on EVERY call it has ever received. Not a rare path: the first one.

IT SURVIVED BECAUSE NOTHING EVER CHOSE IT. `TacticChooser` picks
`recover` zero times; a model shown the Brief also picked it zero times,
because the page ends with doctrine's ranked recommendation and the model
agreed with it. Take that hint away and the model reaches for `recover`
on the first fight --- and the engine dies.

Two defects in two days found the same way, both in kinds doctrine never
picks: `dodge` for a Stunned combatant, and this. A benchmark driven only
by its own catalogue re-tests the catalogue's habits.

`tests/loop/test_newly_wired_kinds.py` lists `recover` among the kinds
"covered by a test here or elsewhere", which was true of the REGISTRATION
and not of the resolver --- the distinction that file's own docstring
draws: "REGISTERED IS NOT THE SAME AS WORKING".
"""
from __future__ import annotations

import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_combat.vitals import apply_vitals_delta
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _winded():
    """A fighter with room to recover --- Recovery is bounded by the gap
    between current and maximum, so a fresh man recovers nothing and the
    test would pass on a no-op."""
    session = CombatSession.create(
        id="r", scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=1),
        combatants=[fighter("tired", side=Side.named("a")),
                    fighter("foe", side=Side.named("b"))],
    ).start()
    hurt = session.combatants["tired"]
    session.combatants["tired"] = apply_vitals_delta(hurt, stun=-12, end=-15)
    return session


def _recover(session):
    return resolve_chosen(
        session, session.combatants["tired"],
        LegalAction(action_id="recover", kind="recover", target_id=None,
                    power_xmlid=None, power_name=None, summary="recover"),
        template=TEMPLATE, roller=RandomRoller(seed=1),
    )


def test_recovering_does_not_raise():
    """The whole defect: it raised on every call."""
    assert _recover(_winded()) is not None


def test_it_gives_stun_back():
    session = _winded()
    before = session.combatants["tired"].state.current_stun
    after = _recover(session).session.combatants["tired"].state.current_stun
    assert after > before


def test_it_gives_end_back():
    session = _winded()
    before = session.combatants["tired"].state.current_end
    after = _recover(session).session.combatants["tired"].state.current_end
    assert after > before


def test_it_reaches_the_log():
    """A Recovery nothing records is one a replay cannot draw --- the same
    defect class as the movement the loop never logged."""
    after = _recover(_winded()).session
    assert any(getattr(e, "kind", "") == "RecoveryTaken"
               for e in after.event_log)
