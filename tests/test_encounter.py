"""Tests for Encounter -- the engine's Segment/Turn clock."""
from kirby_combat.encounter import Encounter


def test_advancing_within_a_turn_increments_the_segment():
    e = Encounter(id="e1", turn=1, segment=3)
    assert e.advance_segment().segment == 4


def test_segment_12_wraps_to_segment_1_of_the_next_turn():
    """6E2 p.18: a Turn consists of 12 Segments."""
    e = Encounter(id="e1", turn=1, segment=12)
    nxt = e.advance_segment()
    assert (nxt.turn, nxt.segment) == (2, 1)


def test_a_new_encounter_starts_on_segment_12():
    """6E2 p.20: combat always begins on Segment 12."""
    assert Encounter(id="e1").segment == 12


def test_advance_returns_a_new_encounter_and_does_not_mutate():
    e = Encounter(id="e1", turn=1, segment=3)
    e.advance_segment()
    assert e.segment == 3


def test_an_encounter_can_exist_with_no_sessions():
    """6E2 p.8 allows a precisely-timed sequence that is not a fight
    ("or some other sequence you need to detail precisely")."""
    assert Encounter(id="e1").sessions == []


def test_the_campaigns_tie_rule_reaches_the_sort():
    """Previously dormant: template.tie_rule was declared and read by
    nothing, because no Campaign existed to plumb it from.

    EGO is set INVERSELY to INT (alice: int=10/ego=18, bob: int=18/ego=10)
    so a pass cannot be EGO ordering in disguise -- this codebase already
    shipped a test that asserted INT ordering while actually feeding EGO,
    and it passed regardless of what the INT rule did.
    """
    from dataclasses import replace

    from kirby_combat.campaign import Campaign
    from kirby_combat.session.tie_rule import TieRule
    from kirby_combat.template import DEFAULT_TEMPLATE
    from tests.fixtures.synthetic_hero import synthetic_combatant

    c = Campaign(
        id="c1", name="X",
        template=replace(DEFAULT_TEMPLATE, tie_rule=TieRule.INT_THEN_PRE),
    )
    e = Encounter(id="e1", segment=3)
    alice = synthetic_combatant(id="alice", name="Alice", spd=4, dex=15, int_=10, ego=18)
    bob = synthetic_combatant(id="bob", name="Bob", spd=4, dex=15, int_=18, ego=10)

    order = e.acting_order([alice, bob], campaign=c)

    assert [s.combatant_id for s in order] == ["bob", "alice"]


def test_a_different_tie_rule_produces_a_different_order():
    """Proves the template is actually consulted: swapping the campaign's
    tie_rule to TieRule.DEX_ROLL (6E2 p.21's book default) for the same
    tied combatants flips the order relative to the INT_THEN_PRE test
    above -- if `acting_order` ignored the template and always used
    whatever `build_acting_order_for_segment`'s own default is, this
    would come back identical to the other test's result.
    """
    from dataclasses import replace

    from kirby_combat.campaign import Campaign
    from kirby_combat.session.tie_rule import TieRule
    from kirby_combat.template import DEFAULT_TEMPLATE
    from tests.fixtures.synthetic_hero import synthetic_combatant

    c = Campaign(
        id="c2", name="Y",
        template=replace(DEFAULT_TEMPLATE, tie_rule=TieRule.DEX_ROLL),
    )
    e = Encounter(id="e2", segment=3)
    alice = synthetic_combatant(id="alice", name="Alice", spd=4, dex=15, int_=10, ego=18)
    bob = synthetic_combatant(id="bob", name="Bob", spd=4, dex=15, int_=18, ego=10)

    calls = {"n": 0}

    def roller():
        calls["n"] += 1
        # Scripted so alice's DEX-Roll margin beats bob's, in the input
        # order the tie_scores loop consumes rolls (alice, then bob) --
        # see `build_provisional_order_for_segment`'s docstring for why
        # that consumption order is guaranteed for same-DEX combatants.
        return [1, 1, 1] if calls["n"] == 1 else [6, 6, 6]

    order = e.acting_order([alice, bob], campaign=c, roller=roller)

    assert [s.combatant_id for s in order] == ["alice", "bob"]
