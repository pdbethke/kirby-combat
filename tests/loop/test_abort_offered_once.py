"""One Abort a Phase, and the menu has to know it.

`mark_aborting` is the single choke point for every reactive abort ---
Dodge, Block and Dive For Cover all route through it --- and it REFUSES a
second one: "combatant 'x' has already aborted this phase". Enumeration
never asked. So the menu offered Dodge to a fighter who had already
aborted, a chooser took it, and the resolver raised `ValueError` out of
the middle of the turn loop, past `on_unresolvable="skip"`, killing the
fight.

Latent until 2026-09-08. It took a fighter dodging twice in one Phase to
surface it, and nothing made that likely until side morale changed which
tactics fire --- Billy Clanton, on a side that had just broken, chose
Dodge twice and brought down the O.K. Corral benchmark.

The same rule this engine keeps relearning: an offer the engine will
refuse is worse than no offer, because something downstream believes it.
Enumeration already applies exactly this reasoning to melee at range, to
Pushing a Power with no END, and to cover a man is already behind.
"""
from __future__ import annotations

from conftest import fighter, session_of          # tests/loop/conftest.py
from kirby_combat.actions.reactive.abort import mark_aborting
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.side import Side


def _menu(session, actor_id="a"):
    """As the loop calls it: session-derived facts are computed by the
    caller and passed in, which is how `actor_holding` and the lockout
    ids already reach enumeration. Enumeration stays pure."""
    from kirby_combat.actions.reactive.abort import is_aborting
    from kirby_combat.statuses import stunned_or_recovering_for

    # `already_aborted` became `can_abort` --- ONE question, because
    # `mark_aborting` refuses for two reasons and gating only this one let
    # 6E2 p.106's Stunned clause escape as a ValueError. This helper
    # mirrors the driver, so it asks the whole question too.
    actor = session.combatants[actor_id]
    enemies = [c for c in session.combatants.values() if c.id != actor_id]
    return enumerate_actions(actor, enemies, can_abort=not (
        is_aborting(session, actor_id)
        or stunned_or_recovering_for(session, actor_id)
    ))


def _kinds(menu):
    return {a.kind for a in menu}


def test_dodge_is_offered_to_a_fighter_who_has_not_aborted():
    """Guards the guard: the ordinary case must keep working."""
    session = session_of(fighter("a", side=Side.named("x")),
                         fighter("b", side=Side.named("y")))
    assert "dodge" in _kinds(_menu(session))


def test_dodge_is_not_offered_twice_in_one_phase():
    """The defect. `mark_aborting` will refuse, so the menu must not
    promise it."""
    session = session_of(fighter("a", side=Side.named("x")),
                         fighter("b", side=Side.named("y")))
    session, _ = mark_aborting(session, "a", to_action="dodge")
    assert "dodge" not in _kinds(_menu(session))


def test_a_fighter_who_has_aborted_still_has_a_menu():
    """He has aborted, not been removed from the fight -- and a combatant
    with an empty menu raises out of the loop."""
    session = session_of(fighter("a", side=Side.named("x")),
                         fighter("b", side=Side.named("y")))
    session, _ = mark_aborting(session, "a", to_action="dodge")
    assert _menu(session), "aborting must not empty the menu"


def test_without_a_session_the_offer_stands():
    """Enumeration is called without this fact all over this suite, and
    must not invent an abort it was never told about."""
    actor = fighter("a", side=Side.named("x"))
    menu = enumerate_actions(actor, [fighter("b", side=Side.named("y"))])
    assert "dodge" in {a.kind for a in menu}
