"""A man shot through and left at 0 BODY has to get worse.

6E2 p.109: "A character at or below 0 BODY is dying. He loses 1 BODY each
Turn (at the end of Segment 12) ... Death occurs when, either due to
attacks or 'bleeding to death,' the character has lost twice his original
BODY."

The end of Segment 12 is exactly where the engine already fires the free
Post-Segment 12 Recovery (6E2 p.131) --- and that hook only ever handed
STUN back. So a dying man lay at -2 BODY for the whole fight, never got
worse, never reached Death by attrition, and could not be saved either,
because nothing could stabilize a condition that was not deteriorating.

In a Western that is not a detail. Three men went down at the O.K. Corral
and the engine had no rule that could kill any of them after the shooting
stopped.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.encounter import Encounter
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import RAW_HEROIC
from kirby_combat.vitals import apply_vitals_delta
from kirby_dice import RandomRoller


def _turn_ending_with(body_by_id: dict[str, int]):
    """One fight, wound the named men, and end the Turn on them."""
    combatants = [fighter("hurt", side=Side.named("a")),
                  fighter("well", side=Side.named("b"))]
    session = CombatSession.create(
        id="b", scene=None, template=RAW_HEROIC,
        dice_roller=RandomRoller(seed=3), combatants=combatants).start()
    for cid, body in body_by_id.items():
        c = session.combatants[cid]
        session.combatants[cid] = apply_vitals_delta(
            c, body=body - c.state.current_body)

    encounter = Encounter(id="e", turn=1, segment=12, sessions=[session],
                          template=RAW_HEROIC)
    return encounter.advance_segment().sessions[0]


def test_a_dying_man_loses_a_body_at_the_end_of_the_turn():
    after = _turn_ending_with({"hurt": 0})
    assert after.combatants["hurt"].state.current_body == -1


def test_he_keeps_losing_it():
    after = _turn_ending_with({"hurt": -3})
    assert after.combatants["hurt"].state.current_body == -4


def test_a_man_with_body_left_does_not_bleed_out():
    """p.122, from the other side: "A foe with positive BODY never bleeds
    (unless you use the optional Bleeding rules)"."""
    after = _turn_ending_with({"hurt": 2})
    assert after.combatants["hurt"].state.current_body == 2


def test_the_bleed_is_in_the_log():
    """A man who quietly got worse between Segments is indistinguishable
    from a bookkeeping error, both to a reader and to a replay."""
    after = _turn_ending_with({"hurt": -1})
    kinds = [getattr(e, "kind", "") for e in after.event_log]
    assert "BleedingSuffered" in kinds, kinds


def test_a_corpse_stops_bleeding():
    """Past -max BODY he is Dead (6E2 p.109) and there is nothing left to
    lose; continuing to subtract is bookkeeping on a corpse -- and it
    would drive a replay's status card further and further negative
    forever.

    This test exists because the guard was written against
    `state.max_body`, which no real combatant has, so it never fired once
    while the suite stayed green.
    """
    combatants = [fighter("hurt", side=Side.named("a")),
                  fighter("well", side=Side.named("b"))]
    session = CombatSession.create(
        id="d", scene=None, template=RAW_HEROIC,
        dice_roller=RandomRoller(seed=3), combatants=combatants).start()
    dead_at = -session.combatants["hurt"].max_body
    c = session.combatants["hurt"]
    session.combatants["hurt"] = apply_vitals_delta(
        c, body=dead_at - c.state.current_body)

    after = Encounter(id="e", turn=1, segment=12, sessions=[session],
                      template=RAW_HEROIC).advance_segment().sessions[0]
    assert after.combatants["hurt"].state.current_body == dead_at


def test_the_guard_can_actually_find_the_threshold():
    """`max_body_of` returning None would disable the guard silently."""
    from kirby_combat.encounter import max_body_of

    assert max_body_of(fighter("x", side=Side.named("a"))) is not None
