"""Mental combat pipeline — OMCV vs DMCV."""
import pytest

from kirby_combat.mental.mental_combat import resolve_mental_to_hit
from kirby_combat.models import StatBlockCombatant


# NOT synthetic: test_mental_to_hit_uses_omcv_not_ocv below reconstructs a
# combatant via type(a)(**a.__dict__), which only round-trips through the
# flat StatBlockCombatant constructor's kwargs shape.
def _mentalist(id_: str, omcv: int = 8) -> StatBlockCombatant:
    return StatBlockCombatant(
        id=id_, name=id_, ocv=0, dcv=0, omcv=omcv, dmcv=3,
        spd=4, dex=15, ego=18, str_=10, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=40,
        current_stun=30, current_body=15, current_end=40,
        is_mentalist=True,
    )


def _target(id_: str, dmcv: int = 5) -> StatBlockCombatant:
    return StatBlockCombatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=3, dmcv=dmcv,
        spd=3, dex=12, ego=10, str_=15, con=15, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=3, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def test_mental_to_hit_hits_on_11_minus():
    result = resolve_mental_to_hit(
        attacker=_mentalist("a", omcv=8),
        target=_target("t", dmcv=5),
        dice_values=[4, 4, 3],   # 11
    )
    assert result.hit is True
    assert result.roll == 11
    assert result.target_number == 11 + 8 - 5


def test_mental_to_hit_misses_on_too_high_roll():
    result = resolve_mental_to_hit(
        attacker=_mentalist("a", omcv=8),
        target=_target("t", dmcv=5),
        dice_values=[6, 6, 6],   # 18
    )
    assert result.hit is False


def test_mental_to_hit_uses_omcv_not_ocv():
    a = _mentalist("a", omcv=10)
    a = type(a)(**{**a.__dict__, "ocv": 0})
    result = resolve_mental_to_hit(
        attacker=a, target=_target("t", dmcv=5),
        dice_values=[4, 4, 3],
    )
    assert result.effective_ocv == 10
    assert result.hit is True


def test_mental_attack_requires_mentalist_flag_on_attacker():
    non_mentalist = _target("nope", dmcv=5)
    with pytest.raises(ValueError, match="mentalist"):
        resolve_mental_to_hit(
            attacker=non_mentalist, target=_target("t", dmcv=5),
            dice_values=[3, 3, 3],
        )


def test_mental_attack_line_of_sight_not_required_by_default():
    a = _mentalist("a", omcv=8)
    t = _target("t", dmcv=5)
    result = resolve_mental_to_hit(attacker=a, target=t, dice_values=[3, 3, 4])
    assert result.hit is True


def test_mental_range_does_not_apply_default():
    a = _mentalist("a", omcv=8)
    t = _target("t", dmcv=5)
    result = resolve_mental_to_hit(
        attacker=a, target=t, dice_values=[4, 4, 3], distance_m=500,
    )
    assert result.range_penalty == 0
    assert result.hit is True
