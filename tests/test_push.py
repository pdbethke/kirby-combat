"""Pushing: temporary points, paid for in END, gone at the end of the Phase."""
from kirby_combat.actions.push import PUSH_END_PER_POINT, push_contribution


def test_a_push_contributes_the_points_pushed():
    c = push_contribution("STR", 5)
    assert c.xmlid == "STR"
    assert c.delta == 5.0


def test_a_push_is_not_conditional_on_identity():
    # Pushing is something the character DOES, not something their costume
    # grants — it applies whoever they currently are.
    c = push_contribution("STR", 5)
    assert c.requires_hero_id is False


def test_the_source_label_says_it_was_pushed():
    assert "push" in push_contribution("STR", 5).source_label.lower()


def test_pushing_nothing_contributes_nothing():
    assert push_contribution("STR", 0).delta == 0.0


def test_the_books_worked_example_push_costs_one_end_per_point():
    # 6E2 p136 works a Push of STR 30 up to STR 40 and prices the whole use
    # at 13 END: 3 for using STR 30 normally, plus 10 for the 10 points
    # Pushed. Only the second half is this module's to answer -- the base
    # END for an ability's normal use is not Pushing's rule -- so that is
    # what this pins.
    points_pushed = 10
    assert push_contribution("STR", points_pushed).delta == 10.0
    assert points_pushed * PUSH_END_PER_POINT == 10
