"""Mental Entangle is 6E1 p.219's Mental Paralysis: counted BODY, MD per die."""
import pytest

from kirby_combat.mental.mental_entangle import roll_mental_paralysis
from tests.fixtures.synthetic_hero import synthetic_combatant


def _mentalist(id_: str = "a", *, mentalist: bool = True):
    return synthetic_combatant(
        id=id_, name=id_, ocv=0, dcv=0, omcv=8, dmcv=3,
        spd=4, dex=15, ego=18, str_=10, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=40,
        current_stun=30, current_body=15, current_end=40,
        is_mentalist=mentalist,
    )


def _target(md: int = 0):
    return synthetic_combatant(
        id="t", name="t", ocv=8, dcv=8, omcv=3, dmcv=5,
        spd=3, dex=12, ego=10, str_=15, con=15, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=md, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def test_body_is_the_normal_damage_count_not_the_pips():
    """6E1 p.217 + 6E2 p.100: 1 -> 0, 2-5 -> 1, 6 -> 2."""
    r = roll_mental_paralysis(_mentalist(), _target(), [1, 4, 6, 6])
    assert r.body == 5


def test_the_targets_mental_defense_does_not_reduce_it():
    """6E1 p.219: MD "offers no other protection against" Mental Paralysis."""
    assert roll_mental_paralysis(_mentalist(), _target(md=20), [4, 4, 4]).body == 3


def test_it_has_one_point_of_mental_defense_per_die():
    assert roll_mental_paralysis(_mentalist(), _target(), [4, 4, 4, 4]).md == 4


def test_only_a_mentalist_can_use_it():
    with pytest.raises(ValueError):
        roll_mental_paralysis(_mentalist(mentalist=False), _target(), [4])
