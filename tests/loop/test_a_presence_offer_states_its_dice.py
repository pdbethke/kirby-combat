"""A Presence Attack offer states the dice the engine will roll.

Found 2026-11-10: Plague (PRE 20) was offered "PRE 20 -> 4d6 vs target's
PRE" every time. The engine rolls PRE/5 less 1d6 in combat (6E2 p.138) and
1d6 less again for each earlier Presence Attack at the same man (6E2
p.140): 3d6, then 2d6. The page promised a die more than any roll he made.
The offer now reads `pre_attacks.landing.presence_dice`, the resolver's own.
"""
from __future__ import annotations

from conftest import blast                                     # tests/loop/conftest.py
from shaped import Dice, armed, encounter_on, scene_with      # tests/loop/shaped.py
from kirby_combat.loop import run_phase
from kirby_combat.side import Side
from kirby_combat.squads import KEEP_ORDERS

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


class _Shouts:
    def __init__(self):
        self.menus = []

    def give_orders(self, page):
        return KEEP_ORDERS

    def choose(self, situation):
        if situation.out_of_turn is not None:
            return situation.menu[0].action_id
        shout = [o for o in situation.menu if o.kind == "presence_attack"]
        if situation.actor.id != "a" or not shout:
            # A Presence Attack takes no time (6E2 p.137): the rest of his
            # Phase comes back without one, and he Dodges it away.
            return next(o.action_id for o in situation.menu if o.kind == "dodge")
        self.menus.append(list(situation.menu))
        return next(o.action_id for o in situation.menu if o.kind == "presence_attack")


def _menus(phases: int):
    scene = scene_with({"a": (0, 0, 0), "b": (5, 0, 0), "c": (6, 0, 0)})
    enc = encounter_on(scene,
                       armed("a", blast("a-eb", 4), side=VILLAINS, dex=30, pre=20),
                       armed("b", None, side=HEROES, dex=10, pre=40),
                       armed("c", None, side=HEROES, dex=10, pre=40))
    seat = _Shouts()
    while len(seat.menus) < phases:
        enc = run_phase(enc, seat, roller=Dice(face=1), on_unresolvable="raise").encounter
    return seat.menus


def _offer(menu, kind, target=None):
    return next(o for o in menu if o.kind == kind and o.target_id == target)


def test_the_first_presence_attack_offers_three_dice_not_four():
    first = _menus(1)[0]
    single = _offer(first, "presence_attack", "b")
    assert "3d6" in single.summary and "4d6" not in single.summary, single.summary
    assert "6E2 p.138" in single.summary


def test_a_repeat_offers_a_die_less_and_says_why():
    second = _menus(2)[1]
    shouted = next(o for o in second if o.kind == "presence_attack"
                   and "2d6" in o.summary)
    assert "1 earlier" in shouted.summary and "6E2 p.140" in shouted.summary, shouted.summary
    group = _offer(second, "presence_attack_group")
    assert "2d6" in group.summary and "3d6" in group.summary, group.summary
