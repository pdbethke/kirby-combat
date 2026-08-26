"""TieRule tests: campaign-selectable DEX-tie resolution (6E2 p.21)."""
from fixtures.synthetic_hero import synthetic_combatant

from kirby_combat.session.tie_rule import TieRule, dex_roll_target
from kirby_combat.session.timeline import build_acting_order_for_segment
from kirby_combat.template import DEFAULT_TEMPLATE


def _c(
    id_: str, spd: int, dex: int, int_: int = 10, ego: int = 10, pre: int = 10,
) -> "HeroCombatant":
    """Minimal Combatant for tie_rule tests."""
    return synthetic_combatant(
        id=id_, name=id_, ocv=0, dcv=0, omcv=0, dmcv=0,
        spd=spd, dex=dex, ego=ego, int_=int_, str_=10, con=10, pre=pre, rec=5,
        pd=0, ed=0, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=20, max_body=10, max_end=20,
        current_stun=20, current_body=10, current_end=20,
    )


def test_dex_roll_winner_is_the_one_who_makes_it_by_most():
    """6E2 p.21: "The character who succeeds with his DEX Roll by the most
    gets to act first"."""
    a = _c("alice", spd=4, dex=20, int_=10)   # target 13-
    b = _c("bob",   spd=4, dex=20, int_=10)
    rolls = iter([[3, 3, 3], [5, 5, 5]])      # alice makes by 4, bob by 0
    slots = build_acting_order_for_segment(
        [a, b], segment=3, tie_rule=TieRule.DEX_ROLL,
        roller=lambda: next(rolls))
    assert [s.combatant_id for s in slots] == ["alice", "bob"]


def test_dex_roll_target_comes_from_the_canon_primitive():
    """Not 9 + DEX // 5. characteristic_roll ROUNDS: DEX 13 is 12-, not 11-."""
    from kirby_cost.engine.rolls import characteristic_roll
    assert characteristic_roll(13) == 12
    assert dex_roll_target(_c("x", spd=4, dex=13)) == 12


def test_int_then_pre_is_selectable():
    """The GM's opt-out from 6E2 p.21, now an explicit campaign setting."""
    a = _c("alice", spd=4, dex=15, int_=10, ego=18)
    b = _c("bob",   spd=4, dex=15, int_=18, ego=10)
    slots = build_acting_order_for_segment(
        [a, b], segment=3, tie_rule=TieRule.INT_THEN_PRE)
    assert [s.combatant_id for s in slots] == ["bob", "alice"]


def test_template_default_tie_rule_is_the_dex_roll():
    """6E2 p.21's default is the contested roll; INT->PRE is the opt-out."""
    assert DEFAULT_TEMPLATE.tie_rule is TieRule.DEX_ROLL


def test_random_is_not_a_book_rule_but_still_deterministic_under_test():
    """TieRule.RANDOM is the engine's own campaign option (the old
    `randomize_dex_ties` flag), not something the books define. It must
    still take an injected roller rather than calling `random` itself."""
    a = _c("alice", spd=4, dex=15)
    b = _c("bob", spd=4, dex=15)
    rolls = iter([2, 5])
    slots = build_acting_order_for_segment(
        [a, b], segment=3, tie_rule=TieRule.RANDOM,
        roller=lambda: next(rolls))
    assert [s.combatant_id for s in slots] == ["bob", "alice"]


def test_dex_roll_target_reads_stats_dex_field():
    """6E1 p.116: "his Agility Skill Rolls remain 12-" -- Lightning
    Reflexes' effective-DEX boost must never reach this function, only
    the plain characteristic.

    DEX 18 pins a hardcoded expected target (9 + 18/5 = 12.6 -> 13-,
    rounded) rather than restating `dex_roll_target`'s own body: DEX 18
    is exactly a value where round-half-up (13) and truncation (12) give
    different answers, so this also guards against a regression back to
    `9 + DEX // 5`.
    """
    c = _c("x", spd=4, dex=18)
    assert dex_roll_target(c) == 13
