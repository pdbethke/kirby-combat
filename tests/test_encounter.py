"""Tests for Encounter -- the engine's Segment/Turn clock."""
import pytest

from kirby_combat.encounter import Encounter
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import DEFAULT_TEMPLATE
from tests.fixtures.synthetic_hero import synthetic_combatant


def _scripted_roller():
    """A DEX_ROLL roller that returns a fixed, non-tie-breaking result.

    DEFAULT_TEMPLATE.tie_rule is TieRule.DEX_ROLL (6E2 p.21's default), so
    `resolve_acting_order` calls `roller` once per combatant regardless of
    whether any DEX tie actually exists. None of these tests' fixtures
    share a DEX value, so the actual roll never decides anything -- a
    constant is enough.
    """
    return lambda: [3, 3, 3]


def _session(session_id, combatants):
    """Build a real CombatSession with synthetic combatants at (id, dex).

    SPD 4 (segments_for_spd) has a Phase in Segment 3 -- the segment these
    tests resolve against; SPD 2 does not.
    """
    return CombatSession.create(
        id=session_id,
        combatants=[
            synthetic_combatant(id=cid, name=cid, spd=4, dex=dex)
            for cid, dex in combatants
        ],
        scene=None,
        template=DEFAULT_TEMPLATE,
    )


def _encounter_with_one_session(segment):
    return Encounter(
        id="e1", segment=segment,
        sessions=[_session("a", [("a_high", 20), ("a_low", 10)])],
    )


def _scene_order_ids(encounter):
    return [s.combatant_id for s in encounter.scene_acting_order]


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


def test_acting_order_without_a_campaign_falls_back_to_own_template():
    """`acting_order`'s no-`campaign` branch (`self.template or
    DEFAULT_TEMPLATE`) had zero coverage: both other acting_order tests
    pass `campaign=`. Set `self.template` explicitly and prove it -- not
    DEFAULT_TEMPLATE -- is what gets consulted, via its `tie_rule`."""
    from dataclasses import replace

    from kirby_combat.session.tie_rule import TieRule
    from kirby_combat.template import DEFAULT_TEMPLATE
    from tests.fixtures.synthetic_hero import synthetic_combatant

    own_template = replace(DEFAULT_TEMPLATE, tie_rule=TieRule.INT_THEN_PRE)
    e = Encounter(id="e1", segment=3, template=own_template)
    alice = synthetic_combatant(id="alice", name="Alice", spd=4, dex=15, int_=10, ego=18)
    bob = synthetic_combatant(id="bob", name="Bob", spd=4, dex=15, int_=18, ego=10)

    order = e.acting_order([alice, bob])  # no campaign

    assert [s.combatant_id for s in order] == ["bob", "alice"]


def test_acting_order_without_a_campaign_or_own_template_falls_back_to_default_template():
    """No `campaign`, no `self.template` -> DEFAULT_TEMPLATE, whose
    `tie_rule` is TieRule.DEX_ROLL (6E2 p.21's book default). DEX_ROLL
    requires a roller; asserting the ValueError (deliberately, per the
    task) proves DEFAULT_TEMPLATE -- and not some no-roller-needed rule --
    is what got resolved."""
    from tests.fixtures.synthetic_hero import synthetic_combatant

    e = Encounter(id="e1", segment=3)  # template=None
    alice = synthetic_combatant(id="alice", name="Alice", spd=4, dex=15, int_=10, ego=18)
    bob = synthetic_combatant(id="bob", name="Bob", spd=4, dex=15, int_=18, ego=10)

    with pytest.raises(ValueError):
        e.acting_order([alice, bob])  # no campaign, no roller


def test_run_segment_writes_the_resolved_order_onto_each_session():
    """The gap that made two guards dormant: nothing populated
    session.timeline.acting_order. See session/apply.py's HONEST LIMIT."""
    enc = _encounter_with_one_session(segment=3)
    out = enc.run_segment(roller=_scripted_roller())
    session = out.sessions[0]
    assert session.timeline.acting_order != []
    assert all(s.segment == 3 for s in session.timeline.acting_order)


def test_the_order_is_scene_wide_across_two_sessions():
    """6E2 p.18 counts DEX among the characters with a Phase in the
    Segment; it does not partition by fight. DEX values interleave
    across the two sessions, so a fight-partitioned order would group
    them and fail."""
    a = _session("a", [("a_high", 20), ("a_low", 10)])
    b = _session("b", [("b_mid", 15)])
    enc = Encounter(id="e1", segment=3, sessions=[a, b])
    out = enc.run_segment(roller=_scripted_roller())
    assert _scene_order_ids(out) == ["a_high", "b_mid", "a_low"]


def test_each_session_receives_only_its_own_combatants_slots():
    """A session's timeline describes that fight, not the whole scene."""
    a = _session("a", [("a_high", 20), ("a_low", 10)])
    b = _session("b", [("b_mid", 15)])
    out = Encounter(id="e1", segment=3, sessions=[a, b]).run_segment(
        roller=_scripted_roller())
    assert {s.combatant_id for s in out.sessions[0].timeline.acting_order} == {"a_high", "a_low"}
    assert {s.combatant_id for s in out.sessions[1].timeline.acting_order} == {"b_mid"}


def test_current_slot_index_resets_when_a_new_order_is_built():
    enc = Encounter(id="e1", segment=3, current_slot_index=4,
                    sessions=[_session("a", [("x", 20)])])
    assert enc.run_segment(roller=_scripted_roller()).current_slot_index == 0
