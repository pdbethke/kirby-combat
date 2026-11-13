"""`split_menu.rung_at`: the rung a slot holding some points stands on, the
highest at or under them (6E1 p.406: Kerendor's 9 points in Resistant
Protection buy the 3 PD / 3 ED rung, no more). Public so a seat reads what
a preset enables without restating the rule."""
from __future__ import annotations

from kirby_combat.hero_view import SlotEffect, SlotStep
from kirby_combat.models import PricedSlotView
from kirby_combat.split_menu import rung_at


def _slot():
    steps = tuple(SlotStep(p, f"{p} pts" if p else "", SlotEffect.nothing())
                  for p in (0, 3, 6, 9, 12))
    return PricedSlotView("rp", "Resistant Protection", 12, True, "defense",
                          steps=steps)


def test_a_share_on_a_rung_stands_on_it():
    assert rung_at(_slot(), 9).points == 9


def test_a_share_between_rungs_stands_on_the_one_below():
    assert rung_at(_slot(), 11).points == 9
    assert rung_at(_slot(), 11).display == "9 pts"


def test_nothing_held_is_the_bottom_rung():
    assert rung_at(_slot(), 0).display == ""
