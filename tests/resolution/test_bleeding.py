"""Bleeding — 6E2 p.109's bleed-out, and p.115's optional wound rules.

TWO SEPARATE SYSTEMS, and the engine had neither.

**Bleeding to death (p.109, not optional).** "A character at or below 0
BODY is dying. He loses 1 BODY each Turn (at the end of Segment 12)."
That is the same hook the free Post-Segment 12 Recovery already fires on
(6E2 p.131), which only ever handed STUN back. So a dying man lay at -2
BODY for the rest of the fight and never reached Death by attrition.

**The optional Bleeding rules (p.115).** "Whenever a character loses
BODY, he will Bleed, thus losing STUN and occasionally some extra BODY."
Dice per Turn come from the BODY he has lost, rolled on Segment 1;
"whenever the character rolls a six on any of the dice, he loses an
additional 1 BODY ... the maximum BODY lost from bleeding is 1 BODY per
Turn, even if several sixes are rolled." Blunt or Normal Damage counts
"-1 level on the Bleeding table". Bleeding can stop of its own accord if
the character rests a full Turn and rolls within the Stop Bleeding range.

THE BOOK'S WORKED EXAMPLE IS THE FIRST TEST (p.115): "Andarra has lost 6
BODY. She will lose 2d6 STUN per Turn from Bleeding. Andarra stops to
rest. On Segment 1, she rolls the 2d6 and gets a 2 and a 1, totaling 3
STUN lost. Because she didn't exert herself, and rolled within the
numbers listed under the Stop Bleeding column, she stops Bleeding."

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

import pytest

from kirby_combat.resolution.bleeding import (
    BLEEDING_TABLE, bleed_out_body, bleeding_dice, bleeding_result,
    stops_bleeding,
)


# ---- The book's example --------------------------------------------------

def test_andarra_loses_six_body_and_bleeds_two_dice():
    assert bleeding_dice(6) == 2


def test_andarra_rolls_two_and_one_for_three_stun():
    out = bleeding_result([2, 1])
    assert out.stun_lost == 3
    assert out.body_lost == 0, "no six was rolled"


def test_andarra_rolling_three_is_inside_the_stop_range_for_six_body():
    assert stops_bleeding(total=3, body_lost=6) is True


# ---- The table -----------------------------------------------------------

@pytest.mark.parametrize("body_lost, dice", [
    (1, 1), (5, 1), (6, 2), (10, 2), (11, 3), (15, 3),
    (16, 4), (20, 4), (21, 5), (25, 5), (26, 6), (99, 6),
])
def test_the_dice_column(body_lost, dice):
    assert bleeding_dice(body_lost) == dice


def test_no_wound_means_no_bleeding():
    assert bleeding_dice(0) == 0
    assert bleeding_dice(-3) == 0


def test_normal_damage_is_one_level_down_the_table():
    """p.115: "Blunt weapons or Normal Damage ... considered to be -1
    level on the Bleeding table. Thus, a character who has taken up to 5
    BODY from only Normal Damage will not bleed; at 6-10 BODY, he'll take
    1d6 per Phase"."""
    assert bleeding_dice(5, killing=False) == 0
    assert bleeding_dice(6, killing=False) == 1
    assert bleeding_dice(11, killing=False) == 2


# ---- Sixes cost BODY, and only one of them ------------------------------

def test_a_six_costs_an_extra_body():
    assert bleeding_result([6, 2]).body_lost == 1


def test_several_sixes_still_cost_only_one_body():
    """p.115: "the maximum BODY lost from bleeding is 1 BODY per Turn,
    even if several sixes are rolled"."""
    out = bleeding_result([6, 6, 6, 6])
    assert out.body_lost == 1
    assert out.stun_lost == 24


# ---- Bleeding to death (p.109) ------------------------------------------

def test_a_dying_man_loses_one_body_a_turn():
    assert bleed_out_body(current_body=0) == 1
    assert bleed_out_body(current_body=-4) == 1


def test_a_man_above_zero_body_does_not_bleed_out():
    """p.109's bleed-out is for the DYING. Bleeding from an ordinary wound
    is the separate optional rule above."""
    assert bleed_out_body(current_body=1) == 0


def test_the_stop_ranges_are_the_books():
    assert BLEEDING_TABLE[0].stop_range == (1, 1)
    assert BLEEDING_TABLE[1].stop_range == (2, 5)
    assert BLEEDING_TABLE[5].stop_range == (6, 21)


# ---- Paramedics (6E2 p.109 stabilize, p.115 stop) ------------------------

def test_everyman_paramedics_is_eight():
    """p.115: "even just the Everyman 8- roll"."""
    from kirby_combat.resolution.bleeding import EVERYMAN_PARAMEDICS

    assert EVERYMAN_PARAMEDICS == 8


def test_stabilizing_gets_harder_the_further_below_zero_he_is():
    """p.109: "at -1 for every negative 2 BODY". A dentist with an 11-
    Paramedics roll makes it on 11 at 0 BODY and on 8 at -6."""
    from kirby_combat.resolution.bleeding import stabilize_target

    assert stabilize_target(paramedics_roll=11, current_body=0) == 11
    assert stabilize_target(paramedics_roll=11, current_body=-1) == 11
    assert stabilize_target(paramedics_roll=11, current_body=-2) == 10
    assert stabilize_target(paramedics_roll=11, current_body=-6) == 8


def test_good_care_helps_and_dirt_hurts():
    """p.109's +1 to +3 and -1 to -3, which are judgements, not a table."""
    from kirby_combat.resolution.bleeding import stabilize_target

    # -4 BODY is -2 on the roll, so 11 becomes 9 before circumstances.
    assert stabilize_target(paramedics_roll=11, current_body=-4,
                            circumstances=3) == 12
    assert stabilize_target(paramedics_roll=11, current_body=-4,
                            circumstances=-3) == 6


def test_tools_are_capped_at_the_books_three():
    """p.115 says "up to +3"; a caller asking for +9 does not get it."""
    from kirby_combat.resolution.bleeding import stop_bleeding_target

    assert stop_bleeding_target(paramedics_roll=11, tools=3) == 14
    assert stop_bleeding_target(paramedics_roll=11, tools=9) == 14
    assert stop_bleeding_target(paramedics_roll=11, tools=-9) == 8


def test_andarras_wound_reopens_below_eleven():
    """p.115's second example: 2 Bleeding dice, so the wound reopens on
    less than 9 + 2 = 11. She rolled 13 and it held."""
    from kirby_combat.resolution.bleeding import reopen_target

    assert reopen_target(dice=2) == 11
