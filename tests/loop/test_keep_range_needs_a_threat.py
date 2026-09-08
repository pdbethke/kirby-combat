"""Keeping your distance from a man who cannot reach you anyway.

`keep_range` is "deny the melee threat their attack": stay at range,
shoot, and let them waste Phases closing. It fired whenever ANY enemy
lacked a ranged attack --- and an unarmed man lacks one too.

At the O.K. Corral that meant the Earps spent the historical fight
shooting Billy Claiborne and Ike Clanton, the two Cowboys who were
unarmed and running away, while three armed men shot back. Ike ends that
run dead at BODY -8 and Claiborne survives on BODY 1. Both of them ran and
lived, and neither was ever the reason to hold a firing line.

Being harmless is exactly what makes someone easy to keep range from,
which is why this tactic of all of them needs to ask whether the man is
worth denying. A fighter carrying nothing is not a melee threat in a
gunfight; he is a man leaving.
"""
from __future__ import annotations

from conftest import blast, fighter               # tests/loop/conftest.py
from kirby_combat.models import AttackPower
from kirby_combat.side import Side
from kirby_combat.tactics.base import Situation
from kirby_combat.tactics.library import all_tactics


def _knife(id_="knifeman"):
    c = fighter(id_, side=Side.named("cow"), armed=False)
    c.attacks.append(AttackPower(
        xmlid="HKA", name="Bowie Knife", damage_dice=2,
        half_die=False, plus_one=False, damage_type="killing",
        defense_type="pd", range_m=0.0, uses_str=True, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        is_ranged=False, reach_m=1.0, source_id=f"{id_}-hka",
    ))
    return c


def _tactic():
    return next(t for t in all_tactics() if t.name == "keep_range")


def _situation(*enemies):
    return Situation(actor=fighter("wyatt", side=Side.named("law"), armed=True),
                     allies=[], enemies=list(enemies),
                     current_segment=12, turn=1)


def test_it_fires_against_a_man_with_a_knife():
    """The case it was written for: he can hurt you, but only up close."""
    assert _tactic().applicable(_situation(_knife()))


def test_it_does_not_fire_against_the_unarmed():
    """Ike Clanton and Billy Claiborne, running."""
    unarmed = fighter("ike", side=Side.named("cow"), armed=False)
    assert not _tactic().applicable(_situation(unarmed))


def test_a_gunman_among_them_does_not_make_the_unarmed_worth_denying():
    """Guards the guard from the other side: the tactic is about the
    MELEE enemy, so an armed rival does not license it."""
    unarmed = fighter("ike", side=Side.named("cow"), armed=False)
    gunman = fighter("frank", side=Side.named("cow"), armed=True)
    assert not _tactic().applicable(_situation(unarmed, gunman))


def test_it_still_denies_the_most_dangerous_of_several_melee_threats():
    """The threat fix from earlier today must survive this one."""
    little = _knife("billy")
    big = _knife("frank")
    big.attacks[-1] = AttackPower(
        xmlid="HKA", name="Axe", damage_dice=6, half_die=False, plus_one=False,
        damage_type="killing", defense_type="pd", range_m=0.0, uses_str=True,
        str_min=0, armor_piercing=0, penetrating=0, increased_stun_mult=0,
        is_ranged=False, reach_m=1.0, source_id="frank-hka",
    )
    situation = _situation(little, big)
    assert _tactic().execute(situation).steps[0].target_id == "frank"
