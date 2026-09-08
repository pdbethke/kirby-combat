"""Who should actually run --- `withdraw_when_outmatched`'s gate.

Power Lad, 399.5 points, STR 40, a 6d6 killing attack and 25 rPD that a
Colt Peacemaker cannot scratch, was dropped into the O.K. Corral and
chose `disengage` on his FIRST Phase. He then left the lot and the fight
decided without him.

The gate compared REACH and nothing else: my longest reach doubled is
still less than theirs, so run. His HKA reaches a metre and their
revolvers reach forty, so it fired --- correctly by the letter, and
absurdly. He crosses that lot in one move and kills whoever he touches.

Range is not distance, which is why no geometric patch fixes this: a
40m revolver says nothing about how far away its owner is standing, and
in that lot everybody was two metres apart.

So the gate narrows to what it was always actually about, and what its
own docstring says --- "a man with no gun in a gunfight runs". Being
OUTRANGED is not the trouble; having nothing to fight with is. Ike
Clanton and Billy Claiborne were unarmed. Power Lad is the opposite of
unarmed.

DELIBERATE NARROWING: an armed-but-outranged fighter -- a knife against a
rifle -- no longer gets this tactic. That case wants a different
doctrine, about closing the distance rather than leaving, and inventing
it here on the strength of one gunfight would be guessing. This tactic is
`judgement` basis, not RAW, and it now claims only what it can defend.
"""
from __future__ import annotations

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.models import AttackPower
from kirby_combat.tactics.base import Situation
from kirby_combat.tactics.library import all_tactics
from kirby_combat.side import Side


def _tactic():
    return next(t for t in all_tactics() if t.name == "withdraw_when_outmatched")


def _situation(actor, enemies):
    return Situation(actor=actor, allies=[], enemies=list(enemies),
                     current_segment=12, turn=1)


def _brick(id_="brick"):
    """Melee, short reach, and lethal on contact."""
    c = fighter(id_, side=Side.named("solo"), armed=False)
    c.attacks.append(AttackPower(
        xmlid="HKA", name="Rending and Tearing", damage_dice=6,
        half_die=False, plus_one=False, damage_type="killing",
        defense_type="pd", range_m=0.0, uses_str=True, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        is_ranged=False, reach_m=1.0, source_id="brick-hka",
    ))
    return c


def _gunman(id_="gunman"):
    return fighter(id_, side=Side.named("law"), armed=True)   # blast, 100m


def test_a_man_with_nothing_to_fight_with_withdraws():
    """Ike Clanton. The case the tactic was written for, still firing."""
    assert _tactic().applicable(
        _situation(fighter("ike", side=Side.named("cow"), armed=False),
                   [_gunman()]))


def test_a_brick_who_kills_on_contact_does_not_withdraw():
    """Power Lad. Outreached by every gun in the lot, and the last man in
    it who should be running."""
    assert not _tactic().applicable(_situation(_brick(), [_gunman()]))


def test_nobody_withdraws_from_an_enemy_who_cannot_reach_back():
    """Guards the guard, and was already true: two unarmed men have no
    reason to run from each other."""
    assert not _tactic().applicable(
        _situation(fighter("a", side=Side.named("x"), armed=False),
                   [fighter("b", side=Side.named("y"), armed=False)]))
