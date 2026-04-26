"""Multiple Attack / Sweep / Rapid Fire / Autofire tests."""
import pytest

from kirby_combat.actions.multiple_attack import MultipleAttack, MultiAttackOutcome
from kirby_combat.actions.sweep import Sweep
from kirby_combat.actions.rapid_fire import RapidFire


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


# ---- Autofire (6E2 p44) ----


def test_autofire_single_target_one_roll_margin_2_means_2_hits():
    """Per 6E2 p44: single-target Autofire is ONE roll; hits 1 + (margin/2) times.

    OCV 10, DCV 5, roll 11 → margin = (10+11-11) - 5 = 5; hits 1 + 5//2 = 3.
    """
    from kirby_combat.actions.autofire import resolve_autofire_single_target
    out = resolve_autofire_single_target(
        attacker_ocv=10, target_dcv=5, attacker_roll=11, autofire_shots=5,
    )
    assert out.hit is True
    assert out.margin == 5
    assert out.hit_count == 3


def test_autofire_single_target_capped_at_power_shots():
    """Hit count is capped at the power's shot count even if margin is huge."""
    from kirby_combat.actions.autofire import resolve_autofire_single_target
    # Margin would be very high → cap at autofire_shots (5)
    out = resolve_autofire_single_target(
        attacker_ocv=20, target_dcv=0, attacker_roll=3, autofire_shots=5,
    )
    assert out.hit is True
    assert out.hit_count == 5


def test_autofire_single_target_miss_when_margin_negative():
    """If margin < 0, no shots hit."""
    from kirby_combat.actions.autofire import resolve_autofire_single_target
    out = resolve_autofire_single_target(
        attacker_ocv=5, target_dcv=10, attacker_roll=15, autofire_shots=5,
    )
    assert out.hit is False
    assert out.hit_count == 0


def test_autofire_single_target_exact_match_one_hit():
    """Margin == 0 hits exactly once (1 + 0//2 = 1)."""
    from kirby_combat.actions.autofire import resolve_autofire_single_target
    # OCV 10, DCV 5, roll = 16 → margin = (10+11-16)-5 = 0
    out = resolve_autofire_single_target(
        attacker_ocv=10, target_dcv=5, attacker_roll=16, autofire_shots=5,
    )
    assert out.hit is True
    assert out.margin == 0
    assert out.hit_count == 1


def test_autofire_zero_shots_raises():
    from kirby_combat.actions.autofire import resolve_autofire_single_target
    with pytest.raises(ValueError, match="autofire_shots"):
        resolve_autofire_single_target(
            attacker_ocv=10, target_dcv=5, attacker_roll=10, autofire_shots=0,
        )


# ---- Autofire multi-target (-1 OCV per 2m of line) ----


def test_autofire_multi_target_first_target_no_penalty():
    """First target in a multi-target burst takes no line penalty."""
    from kirby_combat.actions.autofire import (
        resolve_autofire_multi_target, MultiTargetSpec,
    )
    targets = [MultiTargetSpec(target_id="t1", target_dcv=5, distance_to_prev_m=0)]
    results = resolve_autofire_multi_target(
        attacker_ocv=10, targets=targets, attacker_rolls=[11], autofire_shots=5,
    )
    assert len(results) == 1
    assert results[0].line_penalty == 0
    assert results[0].effective_ocv == 10


def test_autofire_multi_target_line_penalty_minus_1_per_2m():
    """Per 6E2 p44: -1 OCV per 2m of line connecting consecutive targets."""
    from kirby_combat.actions.autofire import (
        resolve_autofire_multi_target, MultiTargetSpec,
    )
    # t1 → t2: 4m → -2 OCV. t2 → t3: 6m → cumulative 10m → -5 OCV.
    targets = [
        MultiTargetSpec(target_id="t1", target_dcv=5, distance_to_prev_m=0),
        MultiTargetSpec(target_id="t2", target_dcv=5, distance_to_prev_m=4),
        MultiTargetSpec(target_id="t3", target_dcv=5, distance_to_prev_m=6),
    ]
    results = resolve_autofire_multi_target(
        attacker_ocv=10, targets=targets, attacker_rolls=[10, 10, 10], autofire_shots=5,
    )
    assert results[0].line_penalty == 0
    assert results[0].effective_ocv == 10
    assert results[1].line_penalty == -2
    assert results[1].effective_ocv == 8
    assert results[2].line_penalty == -5
    assert results[2].effective_ocv == 5


def test_autofire_multi_target_more_targets_than_shots_raises():
    from kirby_combat.actions.autofire import (
        resolve_autofire_multi_target, MultiTargetSpec,
    )
    targets = [MultiTargetSpec(target_id=f"t{i}", target_dcv=5) for i in range(6)]
    rolls = [10] * 6
    with pytest.raises(ValueError, match="cannot fire"):
        resolve_autofire_multi_target(
            attacker_ocv=10, targets=targets, attacker_rolls=rolls, autofire_shots=5,
        )
