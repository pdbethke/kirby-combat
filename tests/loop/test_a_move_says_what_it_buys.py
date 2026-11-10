"""A move offer says what it buys a shooter (6E2 p.26, p.40).

Found 2026-11-10, Plague against four UNTIL agents: 0 hits in 7 shots at
-4 OCV, never once closing. His menu offered a `half_move` that said only
"a Half Phase Action, your Phase goes on", and a `move` that called itself
a "Half-move ... cuts range penalty next phase" while being a Full Move.
A Half Move of 12m toward the agent 16.6m off, then a shot, was the play:
it ends 4.6m away, where the Range Modifier is 0, not -4. Nothing on the
page said so. The offer now states where the move ends and the Range
Modifier there, from the same calls the resolver and the to-hit roll make.
"""
from __future__ import annotations

from conftest import blast                                     # tests/loop/conftest.py
from shaped import Dice, armed, encounter_on, scene_with      # tests/loop/shaped.py
from kirby_combat.loop import run_phase
from kirby_combat.side import Side
from kirby_combat.squads import KEEP_ORDERS

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


class _Menu:
    def __init__(self):
        self.menu = None

    def give_orders(self, page):
        return KEEP_ORDERS

    def choose(self, situation):
        if situation.out_of_turn is not None:
            return situation.menu[0].action_id
        self.menu = list(situation.menu)
        return next(a.action_id for a in situation.menu if a.kind == "dodge")


def _menu(distance: float, running: int = 24):
    scene = scene_with({"a": (0, 0, 0), "b": (distance, 0, 0)})
    enc = encounter_on(scene,
                       armed("a", blast("a-eb", 4), side=VILLAINS, dex=30, running=running),
                       armed("b", None, side=HEROES, dex=10))
    seat = _Menu()
    run_phase(enc, seat, roller=Dice(face=3), on_unresolvable="raise")
    return seat.menu


def _offer(menu, kind, mode="running"):
    return next(a for a in menu if a.kind == kind and a.mode == mode and a.target_id == "b")


def test_a_half_move_says_where_it_ends_and_the_range_modifier_there():
    half = _offer(_menu(20.0), "half_move")
    # 12m of a 24m Running toward a man 20m off: 8m from him, Range 0 (-4 now).
    assert "ends 8m from him" in half.summary, half.summary
    assert "Range Modifier 0 there, -4 now" in half.summary, half.summary
    assert "your Phase goes on" in half.summary


def test_a_half_move_that_changes_no_band_says_so_plainly():
    half = _offer(_menu(40.0), "half_move")
    # 28m off after it: -4 there, -6 now.
    assert "ends 28m from him" in half.summary, half.summary
    assert "Range Modifier -4 there, -6 now" in half.summary, half.summary


def test_a_full_move_calls_itself_one_and_promises_no_shot():
    full = _offer(_menu(20.0), "move")
    assert full.summary.startswith("Full Move toward"), full.summary
    assert "Half-move" not in full.summary
    assert "the whole Phase, no attack" in full.summary, full.summary
