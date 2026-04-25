"""Multiple Attack / Sweep / Rapid Fire / Autofire tests."""
import pytest

from kirby_combat.actions.multiple_attack import MultipleAttack, MultiAttackOutcome
from kirby_combat.actions.sweep import Sweep
from kirby_combat.actions.rapid_fire import RapidFire
from kirby_combat.actions.autofire import Autofire


# ---- Multiple Attack ----

def test_multiple_attack_descending_ocv():
    out = MultipleAttack.compute(base_ocv=8, num_targets=3)
    assert out.per_shot_ocv == [8, 6, 4]


def test_multiple_attack_dcv_half():
    out = MultipleAttack.compute(base_ocv=8, num_targets=3)
    assert out.dcv_factor == 0.5


def test_multiple_attack_phase_full():
    out = MultipleAttack.compute(base_ocv=8, num_targets=2)
    assert out.phase_cost == "full"


def test_multiple_attack_one_target_no_penalty():
    out = MultipleAttack.compute(base_ocv=8, num_targets=1)
    assert out.per_shot_ocv == [8]


def test_multiple_attack_zero_targets_raises():
    with pytest.raises(ValueError, match="num_targets"):
        MultipleAttack.compute(base_ocv=8, num_targets=0)


def test_multiple_attack_csl_offset_flattens_penalty():
    # csl_offset=4 means first 3 shots at full OCV (i=0,1,2 → max(0, 0/2/4 - 4) = 0)
    out = MultipleAttack.compute(base_ocv=8, num_targets=4, csl_offset=4)
    assert out.per_shot_ocv == [8, 8, 8, 6]


# ---- Sweep ----

def test_sweep_same_math_as_multiple_attack():
    a = MultipleAttack.compute(base_ocv=8, num_targets=3)
    s = Sweep.compute(base_ocv=8, num_targets=3)
    assert a.per_shot_ocv == s.per_shot_ocv
    assert a.dcv_factor == s.dcv_factor


def test_sweep_name_is_sweep():
    assert Sweep.name == "sweep"


# ---- Rapid Fire ----

def test_rapid_fire_descending_ocv():
    out = RapidFire.compute(base_ocv=10, num_shots=3)
    assert out.per_shot_ocv == [10, 8, 6]


def test_rapid_fire_no_dc_bonus_by_default():
    out = RapidFire.compute(base_ocv=10, num_shots=3)
    assert out.dc_per_shot_bonus == 0


def test_rapid_fire_extra_dc_per_shot_when_opted_in():
    out = RapidFire.compute(base_ocv=10, num_shots=3, extra_dc_per_shot=True)
    assert out.dc_per_shot_bonus == 1


def test_rapid_fire_csl_offset_works():
    out = RapidFire.compute(base_ocv=10, num_shots=4, csl_offset=2)
    # i=0 → 10-max(0, 0-2)=10; i=1 → 10-max(0, 2-2)=10; i=2 → 10-max(0, 4-2)=8; i=3 → 10-max(0, 6-2)=6
    assert out.per_shot_ocv == [10, 10, 8, 6]


def test_rapid_fire_dcv_half():
    out = RapidFire.compute(base_ocv=10, num_shots=3)
    assert out.dcv_factor == 0.5


# ---- Autofire ----

def test_autofire_default_5_shots():
    out = Autofire.compute(base_ocv=10)
    assert len(out.per_shot_ocv) == 5
    assert out.per_shot_ocv == [10, 8, 6, 4, 2]


def test_autofire_dcv_unchanged():
    out = Autofire.compute(base_ocv=10)
    assert out.dcv_factor == 1.0


def test_autofire_csl_levels_offset_penalties():
    # 5 shots, csl_offset=4: i=0..2 full OCV, i=3 -> -2, i=4 -> -4
    out = Autofire.compute(base_ocv=10, num_shots=5, csl_offset=4)
    assert out.per_shot_ocv == [10, 10, 10, 8, 6]


def test_autofire_zero_shots_raises():
    with pytest.raises(ValueError, match="num_shots"):
        Autofire.compute(base_ocv=10, num_shots=0)


def test_autofire_one_shot_no_penalty():
    out = Autofire.compute(base_ocv=10, num_shots=1)
    assert out.per_shot_ocv == [10]
