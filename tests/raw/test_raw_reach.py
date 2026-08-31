"""RAW alignment — Reach.

Each test paraphrases one statement from the rulebook and asserts the engine
agrees with it. No rules text is reproduced.
"""
from kirby_combat.actions.reach import within_reach
from kirby_combat.hero_view import _base_reach_m


class _BareHero:
    powers: list = []


def test_6e2_p56_a_characters_reach_is_one_metre():
    # 6E2 p56 states a character's Reach as one metre around himself.
    assert _base_reach_m(_BareHero()) == 1.0


def test_6e2_p40_within_reach_is_its_own_band_at_one_metre():
    # 6E2 p40's Range Modifier table gives the reach band its own row,
    # distinct from the next band up — so 1m is within Reach and 2m is not.
    assert within_reach(1.0, 1.0).in_reach is True
    assert within_reach(2.0, 1.0).in_reach is False


def test_6e2_p36_beyond_reach_is_not_hand_to_hand():
    # 6E2 p36 divides combat in two: within Reach is HTH, beyond it is Ranged.
    # The engine expresses "not HTH" as a failed reach verdict.
    assert within_reach(1.5, 1.0).in_reach is False


def test_6e1_p231_a_character_without_growth_reaches_one_metre():
    # 6E1 p231 (Growth) states that a character with no Growth can only hit
    # targets within his own Reach, given as 1m.
    assert _base_reach_m(_BareHero()) == 1.0
