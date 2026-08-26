"""Timeline + SPD chart phase resolution tests."""
import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.session.tie_rule import TieRule
from kirby_combat.session.timeline import (
    Timeline,
    ActingSlot,
    ActionIntent,
    build_acting_order_for_segment,
    build_provisional_order_for_segment,
    resolve_acting_order,
    consume_block_priority,
)


def _c(
    id_: str, spd: int, dex: int, int_: int = 10, ego: int = 10, pre: int = 10,
) -> "HeroCombatant":
    """Minimal Combatant for timeline tests."""
    return synthetic_combatant(
        id=id_, name=id_, ocv=0, dcv=0, omcv=0, dmcv=0,
        spd=spd, dex=dex, ego=ego, int_=int_, str_=10, con=10, pre=pre, rec=5,
        pd=0, ed=0, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=20, max_body=10, max_end=20,
        current_stun=20, current_body=10, current_end=20,
    )


def test_spd_6_acts_in_segments_2_4_6_8_10_12():
    from kirby_combat.tables import segments_for_spd
    assert segments_for_spd(6) == frozenset({2, 4, 6, 8, 10, 12})


def test_spd_0_acts_in_no_segments():
    from kirby_combat.tables import segments_for_spd
    assert segments_for_spd(0) == frozenset()


def test_acting_order_higher_dex_first():
    a = _c("alice", spd=4, dex=20)
    b = _c("bob", spd=4, dex=15)
    slots = build_acting_order_for_segment([a, b], segment=3)
    assert [s.combatant_id for s in slots] == ["alice", "bob"]


def test_acting_order_ties_broken_by_int():
    """6E2 p.21: the GM's alternative to a DEX Roll is highest INT first.
    EGO is set INVERSELY to INT so a passing result cannot be EGO ordering
    in disguise -- which is what the previous version of this test was."""
    a = _c("alice", spd=4, dex=15, int_=10, ego=18)
    b = _c("bob",   spd=4, dex=15, int_=18, ego=10)
    slots = build_acting_order_for_segment([a, b], segment=3)
    assert [s.combatant_id for s in slots] == ["bob", "alice"]


def test_equal_int_falls_through_to_pre():
    """6E2 p.21: "if their INTs are also tied, use PRE"."""
    a = _c("alice", spd=4, dex=15, int_=12, pre=10)
    b = _c("bob",   spd=4, dex=15, int_=12, pre=20)
    slots = build_acting_order_for_segment([a, b], segment=3)
    assert [s.combatant_id for s in slots] == ["bob", "alice"]


def test_equal_int_and_pre_is_stable_by_id():
    a = _c("bravo", spd=4, dex=15, int_=12, pre=12)
    b = _c("alpha", spd=4, dex=15, int_=12, pre=12)
    slots = build_acting_order_for_segment([a, b], segment=3)
    assert [s.combatant_id for s in slots] == ["alpha", "bravo"]


def test_int_is_carried_independently_of_ego():
    """INT was never a field on CombatStats, which made timeline's
    tiebreak branch unreachable (spec 2.1). Distinct values prove INT is
    its own field and not aliased onto EGO."""
    c = _c("alice", spd=4, dex=15, int_=18, ego=7)
    stats = c.combat_stats()
    assert stats.int_ == 18
    assert stats.ego == 7


def test_acting_order_excludes_combatants_without_phase_in_segment():
    a = _c("alice", spd=2, dex=20)  # acts only in 6, 12
    b = _c("bob", spd=4, dex=15)    # acts in 3, 6, 9, 12
    slots = build_acting_order_for_segment([a, b], segment=3)
    assert [s.combatant_id for s in slots] == ["bob"]


def test_acting_order_empty_when_no_one_has_phase():
    a = _c("alice", spd=2, dex=20)
    slots = build_acting_order_for_segment([a], segment=5)
    assert slots == []


def test_acting_slot_has_dex_and_int_snapshot():
    a = _c("alice", spd=4, dex=18, int_=11)
    slots = build_acting_order_for_segment([a], segment=3)
    assert slots[0].dex_at_phase == 18
    assert slots[0].int_tiebreak == 11
    assert slots[0].has_acted is False


def test_no_intents_resolves_to_the_provisional_order():
    """The wrapper must be a true no-op so existing callers are unaffected."""
    a = _c("a", spd=4, dex=20)
    b = _c("b", spd=4, dex=15)
    cs = [a, b]
    prov = build_provisional_order_for_segment(cs, segment=3)
    final = resolve_acting_order(prov, intents={})
    assert [s.combatant_id for s in final] == [s.combatant_id for s in prov]


def test_no_intents_resolve_matches_wrapper_with_ties_and_tie_rule():
    """Same DEX (a tie) plus a NON-default tie_rule (RANDOM, which also
    requires a roller) actually run through the wrapper, to catch a
    wrapper that drops a combatant, reorders one, or fails to forward
    `tie_rule`/`roller` through to the resolution pass. INT_THEN_PRE would
    not do this: it is also the default for both functions, so a wrapper
    that silently swallowed `tie_rule` would still happen to produce the
    right answer. RANDOM cannot pass by accident -- with no roller
    forwarded it raises `ValueError` instead of silently falling back to
    the INT_THEN_PRE default, and if `roller` weren't forwarded either,
    the two paths below would consume the scripted rolls in diverging
    ways and disagree."""
    a = _c("a", spd=4, dex=15, int_=12, pre=10)
    b = _c("b", spd=4, dex=15, int_=8, pre=20)
    c = _c("c", spd=4, dex=18)
    cs = [a, b, c]

    # RANDOM's roller is called once per slot (not just the tied pair):
    # the provisional order for this input is [c, a, b] (c's DEX 18 sorts
    # first; a/b's tied DEX 15 keeps their input order), so these three
    # scripted rolls land as c=2, a=5, b=9 in both calls below.
    rolls_for_wrapped = iter([2, 5, 9])
    wrapped = build_acting_order_for_segment(
        cs, segment=3, tie_rule=TieRule.RANDOM, roller=lambda: next(rolls_for_wrapped))

    prov = build_provisional_order_for_segment(cs, segment=3)
    rolls_for_resolved = iter([2, 5, 9])
    resolved = resolve_acting_order(
        prov, intents={}, tie_rule=TieRule.RANDOM, roller=lambda: next(rolls_for_resolved))

    assert [s.combatant_id for s in wrapped] == [s.combatant_id for s in resolved]
    # highest DEX first (c); the a/b DEX tie broken by the scripted RANDOM
    # rolls (a=5, b=9 -> b's higher roll wins)
    assert [s.combatant_id for s in wrapped] == ["c", "b", "a"]
    assert len(wrapped) == 3


def test_mental_action_orders_on_ego_not_dex():
    """APG p.50: mental combat and mental powers "use EGO to determine who
    acts first". The telepath has the lower DEX and the higher EGO."""
    brick    = _c("brick",   spd=4, dex=20, ego=8)
    telepath = _c("telepath", spd=4, dex=10, ego=25)
    prov = build_provisional_order_for_segment([brick, telepath], segment=3)
    final = resolve_acting_order(prov, intents={
        "telepath": ActionIntent(action_type="MINDCONTROL", is_mental=True),
        "brick": ActionIntent(action_type="STRIKE"),
    })
    assert [s.combatant_id for s in final] == ["telepath", "brick"]


def test_mental_ordering_is_scoped_to_the_declared_action_not_the_combatant():
    """APG p.50's EGO ordering applies to the *action*, not the actor: a
    telepath who throws a punch (a non-mental intent) still orders on DEX,
    same as anyone else. Without scoping, this would regress to the old
    'sort everything on EGO' bug the engine used to have (spec history)."""
    brick    = _c("brick",   spd=4, dex=20, ego=8)
    telepath = _c("telepath", spd=4, dex=10, ego=25)
    prov = build_provisional_order_for_segment([brick, telepath], segment=3)
    final = resolve_acting_order(prov, intents={
        "telepath": ActionIntent(action_type="STRIKE", is_mental=False),
        "brick": ActionIntent(action_type="STRIKE"),
    })
    assert [s.combatant_id for s in final] == ["brick", "telepath"]


def test_no_declared_intent_orders_on_dex_as_before():
    """A combatant absent from `intents` (or an entirely empty `intents`
    dict) must behave exactly as it does today: physical, DEX-ordered."""
    brick    = _c("brick",   spd=4, dex=20, ego=8)
    telepath = _c("telepath", spd=4, dex=10, ego=25)
    prov = build_provisional_order_for_segment([brick, telepath], segment=3)
    final = resolve_acting_order(prov, intents={})
    assert [s.combatant_id for s in final] == ["brick", "telepath"]


def test_successful_block_acts_first_despite_lower_dex():
    """6E2 p.60 ("ACTING FIRST"): a successful Block lets the blocker
    "act first (regardless of relative DEX)". The blocker has the LOWER
    DEX here on purpose -- a passing result cannot be ordinary DEX
    ordering in disguise."""
    blocker = _c("blocker", spd=4, dex=10)
    attacker = _c("attacker", spd=4, dex=25)
    slots = build_acting_order_for_segment(
        [blocker, attacker], segment=3,
        acts_first={"blocker": "attacker"})
    assert [s.combatant_id for s in slots] == ["blocker", "attacker"]


def test_block_priority_holds_even_if_the_attacker_does_not_attack():
    """6E2 p.60 applies the priority whether or not the attacker attacks
    again -- so it cannot be modelled as a reaction resolved at attack
    time. The blocker still goes first in a Phase where the attacker
    only moves."""
    blocker = _c("blocker", spd=4, dex=10)
    attacker = _c("attacker", spd=4, dex=25)
    prov = build_provisional_order_for_segment([blocker, attacker], segment=3)
    final = resolve_acting_order(prov, intents={
        "attacker": ActionIntent("MOVE"),
        "blocker": ActionIntent("STRIKE"),
    }, acts_first={"blocker": "attacker"})
    assert [s.combatant_id for s in final] == ["blocker", "attacker"]


def test_block_priority_outranks_the_int_pre_tie_ladder_too():
    """Block priority must be consulted BEFORE any characteristic -- not
    just DEX. Here attacker would win the INT/PRE ladder outright (higher
    INT) if Block priority were not the leading sort key."""
    blocker = _c("blocker", spd=4, dex=10, int_=8, pre=8)
    attacker = _c("attacker", spd=4, dex=25, int_=20, pre=20)
    slots = build_acting_order_for_segment(
        [blocker, attacker], segment=3,
        acts_first={"blocker": "attacker"})
    assert [s.combatant_id for s in slots] == ["blocker", "attacker"]


def test_block_priority_is_consumed_after_one_shared_segment():
    """The priority buys one shared Segment, not a standing advantage.
    `consume_block_priority` is an explicit, separate call -- it returns
    a NEW dict rather than mutating the caller's `state` in place, so the
    caller's own mapping is never touched as a hidden side channel."""
    blocker = _c("blocker", spd=4, dex=10)
    attacker = _c("attacker", spd=4, dex=25)
    state = {"blocker": "attacker"}

    first = build_acting_order_for_segment(
        [blocker, attacker], segment=3, acts_first=state)
    assert [s.combatant_id for s in first] == ["blocker", "attacker"]

    state = consume_block_priority(state, [blocker, attacker], segment=3)
    assert state == {}

    second = build_acting_order_for_segment(
        [blocker, attacker], segment=6, acts_first=state)
    assert [s.combatant_id for s in second] == ["attacker", "blocker"]


def test_block_priority_inert_when_named_attacker_has_no_phase_this_segment():
    """6E2 p.60's priority only fires "if his next Phase and the
    attacker's next Phase fall in the same Segment". A blocker's entry
    naming an attacker who is not acting this Segment must NOT let the
    blocker jump a THIRD combatant who is acting -- the same-Segment
    condition, not just "has an entry", gates the priority."""
    blocker = _c("blocker", spd=4, dex=10)          # acts 3, 6, 9, 12
    absent_attacker = _c("absent", spd=2, dex=25)    # acts 6, 12 only
    other = _c("other", spd=4, dex=20)               # acts 3, 6, 9, 12

    slots = build_acting_order_for_segment(
        [blocker, absent_attacker, other], segment=3,
        acts_first={"blocker": "absent"})
    assert [s.combatant_id for s in slots] == ["other", "blocker"]


def test_block_priority_not_yet_consumed_if_named_attacker_has_no_phase_this_segment():
    """An `acts_first` entry is only spent by a Segment where BOTH the
    blocker and the named attacker have a Phase (6E2 p.60's "same
    Segment" condition) -- not merely by the blocker acting."""
    blocker = _c("blocker", spd=4, dex=10)   # acts 3, 6, 9, 12
    attacker = _c("attacker", spd=2, dex=25)  # acts 6, 12 only
    state = {"blocker": "attacker"}

    # Segment 3: attacker has no Phase here, so the priority is inert
    # (nothing to reorder) AND not yet spent.
    order = build_acting_order_for_segment([blocker, attacker], segment=3)
    assert [s.combatant_id for s in order] == ["blocker"]
    state = consume_block_priority(state, [blocker, attacker], segment=3)
    assert state == {"blocker": "attacker"}

    # Segment 6: both share a Phase -- priority applies and is now spent.
    slots = build_acting_order_for_segment(
        [blocker, attacker], segment=6, acts_first=state)
    assert [s.combatant_id for s in slots] == ["blocker", "attacker"]
    state = consume_block_priority(state, [blocker, attacker], segment=6)
    assert state == {}


def test_block_priority_leapfrogs_an_uninvolved_third_party():
    """Pins this engine's chosen reading of 6E2 p.60's "act first
    (regardless of relative DEX)": ABSOLUTE, not pairwise. The book only
    says the blocker beats the ATTACKER regardless of DEX -- it does not
    say anything about a third combatant who isn't part of the Block at
    all. A pairwise reading would leave the blocker below any higher-DEX
    bystander; this engine's `_block_priority_rank` is a single leading
    sort key with no notion of "against whom", so it puts the blocker
    ahead of EVERYONE with a Phase this Segment, uninvolved bystander
    included. See `resolve_acting_order`'s docstring for why: a true
    pairwise priority is a partial order, not expressible as a sort key,
    and reworking that is out of scope here -- this test exists so the
    absolute behaviour stays pinned in one direction instead of drifting
    unnoticed."""
    blocker = _c("blocker", spd=4, dex=10)
    attacker = _c("attacker", spd=4, dex=12)
    bystander = _c("bystander", spd=4, dex=30)
    slots = build_acting_order_for_segment(
        [blocker, attacker, bystander], segment=3,
        acts_first={"blocker": "attacker"})
    assert [s.combatant_id for s in slots] == ["blocker", "bystander", "attacker"]


def test_timeline_initial_state():
    t = Timeline(turn=1, segment=1, acting_order=[], current_slot_index=0,
                 held_actions=[], aborted_this_phase=set())
    assert t.turn == 1
    assert t.segment == 1
    assert t.current_slot_index == 0
