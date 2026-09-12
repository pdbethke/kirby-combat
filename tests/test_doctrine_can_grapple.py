"""Grab the man, and the four action kinds behind it.

`grab` is offered 10 times in six corral fights and taken zero times.
Behind it sit `escape_str`, `escape_attack` and `release_held`, none of
which has EVER been offered in any benchmark --- because the escape
family needs somebody to be holding somebody, and nobody ever grabs. One
doctrine gap gates four kinds.

The catalogue does hold `grab_and_throw`, and it cannot fire in a
western for two reasons, both correct on their own terms: it wants the
actor's best attack to be MELEE (a gunfighter's best is his revolver)
and it wants STR 30 for "a competitive grab attempt" --- 6d6, a
superhero. Every man at the corral is STR 10.

THIS IS THE OTHER GRAB. Not out-muscling somebody, but seizing the gun
arm of a man standing a metre away so he cannot use it --- which is what
actually happened in the lot, and is a STR-vs-STR contest between equals
rather than a power play. So it gates on REACH and on the man being
armed, not on a STR floor.

It needs `Situation.in_reach`, which did not exist until today: a Grab is
legal only against somebody you can touch, and a tactic that named a man
across the lot had its plan discarded. `disarm_the_armed` shipped
target-less for exactly that reason and has since been given its victim
back.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Situation


class _Stats:
    ocv = dcv = 8
    omcv = dmcv = 5
    max_stun = max_body = max_end = 20
    str_ = con = 15
    dex = ego = int_ = 10
    pre = 15
    spd = 4
    pd = ed = 10
    rpd = red = 2


class _Gun:
    xmlid = "RKA"; name = "Colt revolver"; damage_dice = 2; range_m = 100.0


class _Man:
    def __init__(self, id: str, attacks=(), *, stun: int = 20):
        self.id = id
        self.name = id.title()
        self.attacks = list(attacks)
        self.current_stun = stun
        self.current_body = self.current_end = 20
        self.max_stun = self.max_body = self.max_end = 20

    def combat_stats(self):
        return _Stats()


def _situation(enemies, distances=None) -> Situation:
    return Situation(actor=_Man("wyatt", [_Gun()]), allies=[], enemies=enemies,
                     distances_m=dict(distances or {}), reach_m=2.0)


def _tactic():
    from kirby_combat.tactics.catalog.grab_the_gun_arm import GrabTheGunArm

    return GrabTheGunArm()


def test_an_armed_man_within_reach_is_grabbed():
    assert _tactic().applicable(
        _situation([_Man("tom", [_Gun()])], {"tom": 1.0}))


def test_a_man_across_the_lot_is_not():
    """The whole reason this tactic needed reach on `Situation`."""
    assert not _tactic().applicable(
        _situation([_Man("tom", [_Gun()])], {"tom": 30.0}))


def test_an_unarmed_man_is_not_worth_holding():
    """A Grab spends your Phase and costs you DCV. Ike Clanton ran from
    this fight unarmed; there is no gun arm to seize."""
    assert not _tactic().applicable(
        _situation([_Man("ike", [])], {"ike": 1.0}))


def test_a_downed_man_is_not_grabbed():
    assert not _tactic().applicable(
        _situation([_Man("billy", [_Gun()], stun=0)], {"billy": 1.0}))


def test_the_plan_names_the_man_within_reach():
    plan = _tactic().execute(_situation(
        [_Man("frank", [_Gun()]), _Man("tom", [_Gun()])],
        {"frank": 30.0, "tom": 1.0}))
    assert plan.steps[0].kind == "grab"
    assert plan.steps[0].target_id == "tom"


def test_it_is_registered():
    from kirby_combat.tactics.library import all_tactics

    assert "grab_the_gun_arm" in {t.name for t in all_tactics()}
