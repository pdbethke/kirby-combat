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


def _encounter(*, acts_first, segment):
    """Blocker DEX 10, attacker DEX 25 -- deliberately the LOWER DEX, so a
    pass proves Block priority (6E2 p.60) and cannot be ordinary DEX
    ordering in disguise."""
    return Encounter(
        id="e1", segment=segment, acts_first=acts_first,
        sessions=[_session("s", [("blocker", 10), ("attacker", 25)])],
    )


def _order_ids(encounter):
    return _scene_order_ids(encounter)


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


def test_run_segment_honors_the_campaigns_tie_rule():
    """`run_segment`'s campaign path -- `resolve_template(campaign, self)`
    -- is the payoff of the whole Campaign -> Encounter hierarchy (a
    campaign's tie_rule reaching the sort). Alice/Bob share DEX (15) so the
    order is decided entirely by tie-breaking; INT/EGO are set inversely
    (alice: int=10/ego=18, bob: int=18/ego=10) so this can't pass by
    accident via EGO ordering.

    The campaign's template sets TieRule.INT_THEN_PRE ("highest INT acts
    first", 6E2 p.21) -> bob first. If `run_segment` ignored `campaign`
    and fell back to `self.template or DEFAULT_TEMPLATE`
    (DEFAULT_TEMPLATE.tie_rule is TieRule.DEX_ROLL), the scripted roller
    below returns an identical roll for every combatant, so DEX_ROLL ties
    fall through to alphabetical combatant_id -> alice first. The two
    paths necessarily disagree, so this only passes if the campaign's
    tie_rule actually reached the sort.
    """
    from dataclasses import replace

    from kirby_combat.campaign import Campaign
    from kirby_combat.session.tie_rule import TieRule

    # _session doesn't carry INT/EGO, so build the session directly here.
    a = CombatSession.create(
        id="a",
        combatants=[
            synthetic_combatant(id="alice", name="Alice", spd=4, dex=15, int_=10, ego=18),
            synthetic_combatant(id="bob", name="Bob", spd=4, dex=15, int_=18, ego=10),
        ],
        scene=None,
        template=DEFAULT_TEMPLATE,
    )
    campaign = Campaign(
        id="c1", name="X",
        template=replace(DEFAULT_TEMPLATE, tie_rule=TieRule.INT_THEN_PRE),
    )
    enc = Encounter(id="e1", segment=3, sessions=[a])

    out = enc.run_segment(campaign=campaign, roller=_scripted_roller())

    assert _scene_order_ids(out) == ["bob", "alice"]


def test_a_recorded_block_priority_orders_the_blocker_first():
    """6E2 p.60, "ACTING FIRST": a successful Block lets the blocker act
    first "regardless of relative DEX". Blocker is DEX 10, attacker DEX
    25 -- the LOWER DEX -- so a pass cannot be ordinary DEX ordering."""
    enc = _encounter(acts_first={"blocker": "attacker"}, segment=3)
    out = enc.run_segment(roller=_scripted_roller())
    assert _order_ids(out)[0] == "blocker"


def test_the_priority_is_consumed_after_the_shared_segment():
    """6E2 p.60: the priority buys the ONE shared Segment, not a standing
    advantage -- `consume_block_priority` must spend it."""
    enc = _encounter(acts_first={"blocker": "attacker"}, segment=3)
    after = enc.run_segment(roller=_scripted_roller())
    again = after.run_segment(roller=_scripted_roller())
    assert _order_ids(again)[0] == "attacker"  # back to DEX order


def test_acts_first_defaults_to_an_empty_mapping():
    """Public shape kirby-api constructs directly -- must not require
    this field."""
    assert Encounter(id="e1").acts_first == {}


def test_run_segment_falls_back_to_self_acts_first_when_none_is_passed():
    enc = _encounter(acts_first={"blocker": "attacker"}, segment=3)
    out = enc.run_segment(roller=_scripted_roller())  # no acts_first= kwarg
    assert _order_ids(out)[0] == "blocker"


def test_an_explicit_acts_first_argument_overrides_the_carried_field():
    """Documented choice: an explicit `acts_first=` argument OVERRIDES
    `self.acts_first` rather than merging with it."""
    enc = _encounter(acts_first={"blocker": "attacker"}, segment=3)
    out = enc.run_segment(roller=_scripted_roller(), acts_first={})
    assert _order_ids(out)[0] != "blocker"


def _session_with_vitals(session_id, *, current_stun, current_end, rec=4,
                          max_stun=20, max_end=20):
    """One combatant, segment/DEX irrelevant to these tests -- only the
    vitals `compute_recovery`'s "post_12" branch reads."""
    combatant = synthetic_combatant(
        id="only", name="Only", spd=2, dex=10, rec=rec,
        max_stun=max_stun, max_end=max_end,
        current_stun=current_stun, current_end=current_end,
    )
    return CombatSession.create(
        id=session_id, combatants=[combatant], scene=None, template=DEFAULT_TEMPLATE,
    )


def _only_combatant(encounter):
    session = encounter.sessions[0]
    return session.combatants["only"]


def test_leaving_segment_12_gives_every_combatant_a_recovery():
    """6E2 p.131: all characters get a free Post-Segment 12 Recovery."""
    session = _session_with_vitals("s", current_stun=10, current_end=10)
    enc = Encounter(id="e1", segment=12, sessions=[session])

    out = enc.advance_segment()

    combatant = _only_combatant(out)
    assert combatant.state.current_stun > 10
    assert combatant.state.current_end > 10


def test_a_stunned_combatant_still_recovers():
    """6E2 p.131 says "even Stunned ones" explicitly, so do not filter on
    consciousness. This engine has no separate "Stunned" status distinct
    from the KO threshhold (`Stunnable.is_ko`, kirby_combat/participant.py
    -- 0 STUN or below), so that threshold is what this test exercises."""
    session = _session_with_vitals("s", current_stun=0, current_end=10)
    enc = Encounter(id="e1", segment=12, sessions=[session])

    out = enc.advance_segment()

    assert _only_combatant(out).state.current_stun > 0


def test_no_recovery_when_leaving_a_segment_other_than_12():
    session = _session_with_vitals("s", current_stun=10, current_end=10)
    enc = Encounter(id="e1", segment=5, sessions=[session])

    out = enc.advance_segment()

    assert _only_combatant(out).state.current_stun == 10
    assert _only_combatant(out).state.current_end == 10


def test_post_12_recovery_does_not_exceed_max():
    session = _session_with_vitals(
        "s", current_stun=19, current_end=20, rec=4, max_stun=20, max_end=20,
    )
    enc = Encounter(id="e1", segment=12, sessions=[session])

    out = enc.advance_segment()

    assert _only_combatant(out).state.current_stun == 20
    assert _only_combatant(out).state.current_end == 20


def test_post_12_recovery_emits_a_recovery_taken_event_per_combatant():
    session = _session_with_vitals("s", current_stun=10, current_end=10, rec=4)
    enc = Encounter(id="e1", segment=12, sessions=[session])

    out = enc.advance_segment()

    events = out.sessions[0].event_log
    assert len(events) == 1
    evt = events[0]
    assert evt.kind == "RecoveryTaken"
    assert evt.combatant_id == "only"
    assert evt.stun_recovered == 4
    assert evt.end_recovered == 4


def test_post_12_recovery_uses_the_campaigns_resolved_template():
    """`advance_segment(campaign=...)` resolves the Encounter's template
    via `resolve_template(campaign, self)`, mirroring `run_segment`'s
    campaign path, rather than any per-session `template`. Since
    `compute_recovery` currently ignores its `template` argument (see its
    docstring), this only proves the campaign path is exercised without
    raising -- not yet a distinguishable recovery amount."""
    from kirby_combat.campaign import Campaign

    session = _session_with_vitals("s", current_stun=10, current_end=10)
    enc = Encounter(id="e1", segment=12, sessions=[session])
    campaign = Campaign(id="c1", name="X", template=DEFAULT_TEMPLATE)

    out = enc.advance_segment(campaign=campaign)

    assert _only_combatant(out).state.current_stun > 10
