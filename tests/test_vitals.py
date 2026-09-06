"""``apply_vitals_delta`` — the single fold from a stat delta to a new combatant.

This function replaces two near-identical private copies that had drifted
apart in capability: ``encounter.py::_apply_stun_end_recovery`` (STUN+END,
no BODY) and ``actions/movement/base.py::_decrement_end`` (END only). Both
carried their own long docstring explaining the same
``combatant.state is combatant`` shape dispatch. The tests below pin that
dispatch for both shapes, because getting it wrong is silent: routing a
``StatBlockCombatant`` into the HeroCombatant branch ``replace``s a
``state`` field that does not exist, and routing the other way writes
``current_*`` onto a HeroCombatant where nothing reads them.
"""
from __future__ import annotations

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.models import StatBlockCombatant
from kirby_combat.vitals import apply_vitals_delta


def _hero(stun: int = 40, body: int = 15, end: int = 30):
    """A HeroCombatant — vitals live on a separate ``state`` dataclass."""
    return synthetic_combatant(
        id="hero", name="Hero", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=40, max_body=15, max_end=30,
        current_stun=stun, current_body=body, current_end=end,
    )


def _statblock(stun: int = 40, body: int = 15, end: int = 30) -> StatBlockCombatant:
    """A StatBlockCombatant — its flat ``current_*`` fields ARE its state."""
    return StatBlockCombatant(
        id="mook", name="Mook", ocv=6, dcv=6, omcv=3, dmcv=3,
        spd=3, dex=15, ego=10, str_=15, con=15, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=40, max_body=15, max_end=30,
        current_stun=stun, current_body=body, current_end=end,
    )


# ---- The shape dispatch: both combatant shapes, same call ----

@pytest.mark.parametrize("make", [_hero, _statblock], ids=["hero", "statblock"])
def test_applies_stun_to_either_shape(make):
    c = apply_vitals_delta(make(stun=40), stun=-12)
    assert c.current_stun == 28


@pytest.mark.parametrize("make", [_hero, _statblock], ids=["hero", "statblock"])
def test_applies_body_to_either_shape(make):
    c = apply_vitals_delta(make(body=15), body=-4)
    assert c.current_body == 11


@pytest.mark.parametrize("make", [_hero, _statblock], ids=["hero", "statblock"])
def test_applies_end_to_either_shape(make):
    c = apply_vitals_delta(make(end=30), end=-7)
    assert c.current_end == 23


@pytest.mark.parametrize("make", [_hero, _statblock], ids=["hero", "statblock"])
def test_all_three_at_once(make):
    c = apply_vitals_delta(make(stun=40, body=15, end=30), stun=-5, body=-2, end=-3)
    assert (c.current_stun, c.current_body, c.current_end) == (35, 13, 27)


@pytest.mark.parametrize("make", [_hero, _statblock], ids=["hero", "statblock"])
def test_positive_deltas_restore(make):
    """Recovery is the same fold with the sign flipped — that is the point
    of one helper rather than a damage one and a recovery one."""
    c = apply_vitals_delta(make(stun=10, end=5), stun=+8, end=+5)
    assert (c.current_stun, c.current_end) == (18, 10)


# ---- Purity: the input is never mutated ----

@pytest.mark.parametrize("make", [_hero, _statblock], ids=["hero", "statblock"])
def test_returns_new_combatant_leaving_original_untouched(make):
    original = make(stun=40)
    returned = apply_vitals_delta(original, stun=-15)
    assert original.current_stun == 40, "input combatant was mutated"
    assert returned is not original
    assert returned.current_stun == 25


@pytest.mark.parametrize("make", [_hero, _statblock], ids=["hero", "statblock"])
def test_zero_delta_is_a_no_op_value(make):
    c = apply_vitals_delta(make(stun=40, body=15, end=30))
    assert (c.current_stun, c.current_body, c.current_end) == (40, 15, 30)


# ---- No clamping: negative STUN and BODY are meaningful in 6E ----

@pytest.mark.parametrize("make", [_hero, _statblock], ids=["hero", "statblock"])
def test_stun_goes_negative_rather_than_clamping(make):
    """6E2 p.106: how far below 0 STUN a character is drives how long they
    stay out. Clamping at 0 would destroy that, the same way clamping END
    on spend destroyed the amount really taken."""
    c = apply_vitals_delta(make(stun=10), stun=-25)
    assert c.current_stun == -15


@pytest.mark.parametrize("make", [_hero, _statblock], ids=["hero", "statblock"])
def test_body_goes_negative_rather_than_clamping(make):
    c = apply_vitals_delta(make(body=3), body=-9)
    assert c.current_body == -6


@pytest.mark.parametrize("make", [_hero, _statblock], ids=["hero", "statblock"])
def test_ko_becomes_true_once_stun_reaches_zero(make):
    """``Stunnable.is_ko`` is ``current_stun <= 0`` — at zero, not merely
    below it. Applying damage is what makes that property true; nothing
    else has to emit a KO event for it to hold."""
    assert make(stun=12).is_ko is False
    assert apply_vitals_delta(make(stun=12), stun=-12).is_ko is True
