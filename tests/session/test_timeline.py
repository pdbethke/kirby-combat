"""Timeline + SPD chart phase resolution tests."""
import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.session.tie_rule import TieRule
from kirby_combat.session.timeline import (
    Timeline,
    ActingSlot,
    build_acting_order_for_segment,
    build_provisional_order_for_segment,
    resolve_acting_order,
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


def test_timeline_initial_state():
    t = Timeline(turn=1, segment=1, acting_order=[], current_slot_index=0,
                 held_actions=[], aborted_this_phase=set())
    assert t.turn == 1
    assert t.segment == 1
    assert t.current_slot_index == 0
