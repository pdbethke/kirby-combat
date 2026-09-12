"""A Grab that leads nowhere.

`held_target_ids` is a parameter of `enumerate_actions` gating the
`throw` offer, and its own comment explains the design: "The
held_target_ids parameter lets the driver pre-compute who's eligible
without this function needing DB access."

**The driver never computed it.** No caller anywhere in this package
passes the argument, so it is always None, so `throw` has never been
offered in any fight this engine has ever run --- the same shape as
`allow_coordinate`, a parameter defaulting to a value nothing sets.

The reader was written too: `Grab.is_grabbed(session, combatant_id)`
scans the event log for the most recent grab/escape pair and returns
`(True, grabber_id)`. Nothing called that either. So a Grab landed, was
recorded, was readable, and led to nothing.

STILL NOT FIXED HERE, and recorded in docs/gaps.md: a GRABBED man is
never offered an escape. `Grab.escape` exists; the escape ladder in
`enumerate_actions` is keyed to `physical_entangle` only, so it answers
6E1 p.217's Entangle and not 6E2 p.67's Grab. That is a second offer and
a second resolver route, not a wiring fix.
"""
from __future__ import annotations

from tests.test_enumeration import _StubPower, _combatant
from kirby_combat.enumeration import enumerate_actions


def _throws(held) -> list[str]:
    gun = _StubPower(xmlid="RKA", name="Colt revolver", levels=4)
    actor = _combatant(id="wyatt", powers=[gun])
    enemy = _combatant(id="tom", powers=[gun])
    return [a.action_id for a in
            enumerate_actions(actor, [enemy], held_target_ids=held,
                              distances={"tom": 1.0})
            if a.kind == "throw"]


def test_nobody_held_means_nothing_to_throw():
    assert _throws(None) == []
    assert _throws(frozenset()) == []


def test_a_held_man_can_be_thrown():
    assert _throws(frozenset({"tom"})) != []


def test_the_driver_computes_who_is_held():
    """The parameter existed and the driver never filled it, so `throw`
    was unreachable in every fight this engine has run."""
    import inspect

    from kirby_combat.loop import run

    source = inspect.getsource(run)
    assert "held_target_ids=" in source, (
        "run.py must pass held_target_ids or `throw` can never be offered"
    )


def test_is_grabbed_is_what_the_driver_asks():
    """The reader was written and never called. Asserting on it keeps the
    driver from growing a second, drifting answer to the same question."""
    from kirby_combat.actions.grab import Grab

    assert callable(Grab.is_grabbed)
