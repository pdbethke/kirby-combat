"""The reach rule: HTH requires the target within Reach (6E2 p36, p56)."""
import pytest

from kirby_combat.actions.reach import ReachVerdict, within_reach


def test_target_inside_reach_is_in_reach():
    v = within_reach(distance_m=0.5, reach_m=1.0)
    assert v.in_reach is True
    assert v.shortfall_m == 0.0


def test_target_exactly_at_reach_is_in_reach():
    # A target at exactly reach_m is within Reach: the reach band is
    # inclusive and positions are floats (6E2 p40).
    v = within_reach(distance_m=1.0, reach_m=1.0)
    assert v.in_reach is True


def test_target_beyond_reach_reports_the_shortfall():
    v = within_reach(distance_m=3.4, reach_m=1.0)
    assert v.in_reach is False
    assert v.shortfall_m == pytest.approx(2.4)


def test_float_noise_does_not_push_a_target_out_of_reach():
    # Landing positions are computed, so a "1.0m" gap arrives as 1.0000000004.
    v = within_reach(distance_m=1.0 + 4e-10, reach_m=1.0)
    assert v.in_reach is True


def test_stretching_extends_the_reach_that_is_passed_in():
    # within_reach does not decide what a character's reach IS; it applies
    # whatever reach it is given. Ravel's 8m Stretching (reach 9m) reaches a
    # target that a bare 1m reach does not.
    assert within_reach(distance_m=8.0, reach_m=9.0).in_reach is True
    assert within_reach(distance_m=8.0, reach_m=1.0).in_reach is False


def test_the_verdict_carries_its_inputs_back():
    v = within_reach(distance_m=2.0, reach_m=1.0)
    assert (v.distance_m, v.reach_m) == (2.0, 1.0)


def test_the_rule_is_on_the_import_surface():
    import kirby_combat

    assert kirby_combat.within_reach is within_reach
    assert kirby_combat.ReachVerdict is ReachVerdict


def test_a_bare_character_reaches_one_metre():
    # 6E1 p231 (Growth): a character with no points in Growth can hit only
    # targets within his own Reach, one metre. The engine's old 2m was an
    # uncited inference from hex size.
    from kirby_combat.hero_view import _base_reach_m

    class _Hero:
        powers: list = []

    assert _base_reach_m(_Hero()) == 1.0


def test_stretching_adds_a_metre_per_level_on_top_of_one():
    from kirby_combat.hero_view import _base_reach_m

    class _Stretch:
        xmlid = "STRETCHING"
        levels = 8

    class _Hero:
        powers = [_Stretch()]

    # Ravel: 8 levels -> 8m of stretch, 9m total reach.
    assert _base_reach_m(_Hero()) == 9.0
