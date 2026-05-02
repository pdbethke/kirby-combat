"""Mental Blast — STUN damage vs MD, no BODY/KB."""
import pytest

from kirby_combat.mental.mental_blast import resolve_mental_blast, MentalBlastResult
from fixtures.synthetic_hero import synthetic_combatant as Combatant


def _mentalist(id_: str = "a") -> Combatant:
    return Combatant(
        id=id_, name=id_, ocv=0, dcv=0, omcv=8, dmcv=3,
        spd=4, dex=15, ego=18, str_=10, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=40,
        current_stun=30, current_body=15, current_end=40,
        is_mentalist=True,
    )


def _target(id_: str = "t", md: int = 0, con: int = 15, current_stun: int = 30) -> Combatant:
    return Combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=3, dmcv=5,
        spd=3, dex=12, ego=10, str_=15, con=con, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=md, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=current_stun, current_body=15, current_end=30,
    )


def test_mental_blast_rolls_damage_like_normal_attack():
    a = _mentalist()
    t = _target(md=0)
    r = resolve_mental_blast(a, t, [4, 4, 4, 4, 4])  # 5d6 = 20
    assert r.raw_stun == 20


def test_mental_blast_stun_reduced_by_mental_defense():
    a = _mentalist()
    t = _target(md=8)
    r = resolve_mental_blast(a, t, [4, 4, 4, 4, 4])  # 20 - 8 = 12
    assert r.stun_dealt == 12


def test_mental_blast_no_body_damage():
    a = _mentalist()
    t = _target(md=0)
    r = resolve_mental_blast(a, t, [6, 6, 6, 6, 6, 6])  # 36 STUN, lots of "doubles"
    assert r.body_dealt == 0


def test_mental_blast_no_knockback():
    a = _mentalist()
    t = _target(md=0)
    r = resolve_mental_blast(a, t, [6, 6, 6, 6, 6])  # 30
    assert r.knockback_m == 0.0


def test_mental_blast_can_trigger_stun_if_stun_exceeds_con():
    a = _mentalist()
    # CON 15 target; STUN dealt 16 -> stunned
    t = _target(md=0, con=15)
    r = resolve_mental_blast(a, t, [4, 4, 4, 4])  # 16
    assert r.target_stunned is True


def test_mental_blast_can_KO_target():
    a = _mentalist()
    # current_stun 5, blast dealing 12 -> KO (current goes to -7)
    t = _target(md=0, current_stun=5)
    r = resolve_mental_blast(a, t, [4, 4, 4])  # 12
    assert r.target_ko is True
