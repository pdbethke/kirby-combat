"""Grab and Throw action tests."""
import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller
from kirby_combat.session import CombatSession
from kirby_combat.actions.grab import Grab, GrabResult
from kirby_combat.actions.throw import Throw, ThrowOutcome


def _c(id_: str, str_: int = 15) -> "HeroCombatant":
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=str_, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _session() -> CombatSession:
    return CombatSession.create(
        id="s1",
        combatants=[_c("alice", str_=30), _c("bob", str_=15)],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


# ---- Grab declare (per 6E2 p67: Attack Roll at -1 OCV / -2 DCV) ----


def _grab(s, *, attacker_ocv=8, target_dcv=5, attack_roll=10,
          attacker_str=30, target_str=15):
    """Helper to call Grab with default RAW parameters."""
    return Grab.declare_and_resolve(
        s, attacker_id="alice", target_id="bob",
        attacker_str=attacker_str, target_str=target_str,
        attacker_ocv=attacker_ocv, target_dcv=target_dcv, attack_roll=attack_roll,
    )


def test_grab_succeeds_when_attack_roll_hits_per_6e2_p67():
    """Per 6E2 p67: Grab requires a successful Attack Roll at -1 OCV.

    Attacker OCV 8 → effective 7. Target DCV 5. Roll 11 → 7+11-11 = 7 >= 5 → hit.
    """
    s = _session()
    s2, result = _grab(s, attacker_ocv=8, target_dcv=5, attack_roll=11)
    assert isinstance(result, GrabResult)
    assert result.hit is True
    assert result.success is True
    assert result.effective_ocv == 7   # 8 - 1
    assert result.attacker_id == "alice"
    assert result.target_id == "bob"


def test_grab_fails_when_attack_roll_misses_dcv():
    """If the Attack Roll misses, the Grab fails regardless of STR."""
    s = _session()
    # OCV 8 → effective 7. Target DCV 10. Roll 16 → 7+11-16 = 2 < 10 → miss.
    s2, result = _grab(s, attacker_ocv=8, target_dcv=10, attack_roll=16,
                       attacker_str=100, target_str=5)  # huge STR doesn't help
    assert result.hit is False
    assert result.success is False


def test_grab_str_does_not_determine_initial_success():
    """Per 6E2 p67: STR contest is for ESCAPE only, not initial grab.

    Even with target_str > attacker_str, the Grab can succeed on a hit.
    """
    s = _session()
    s2, result = _grab(s, attacker_ocv=10, target_dcv=5, attack_roll=10,
                       attacker_str=15, target_str=30)
    assert result.hit is True
    assert result.success is True


def test_grab_applies_minus_1_ocv_penalty():
    """Per 6E2 p67: Grab takes a -1 OCV penalty on the Attack Roll."""
    s = _session()
    # OCV 8 → effective 7. Target DCV 7. Roll 12.
    # Without -1: 8+11-12 = 7 >= 7 → hit. With -1: 7+11-12 = 6 < 7 → miss.
    s2, result = _grab(s, attacker_ocv=8, target_dcv=7, attack_roll=12)
    assert result.effective_ocv == 7
    assert result.hit is False


def test_grab_emits_action_declared_and_resolved_events():
    s = _session()
    s2, _ = _grab(s, attack_roll=10)
    kinds = [e.kind for e in s2.event_log]
    assert "ActionDeclared" in kinds
    assert "ActionResolved" in kinds
    declared_ix = kinds.index("ActionDeclared")
    resolved_ix = kinds.index("ActionResolved")
    assert declared_ix < resolved_ix


# ---- is_grabbed ----

def test_is_grabbed_false_initially():
    s = _session()
    assert Grab.is_grabbed(s, "bob") == (False, None)


def test_is_grabbed_true_after_successful_grab():
    s = _session()
    s2, _ = _grab(s, attacker_ocv=10, target_dcv=5, attack_roll=10)
    is_g, by = Grab.is_grabbed(s2, "bob")
    assert is_g is True
    assert by == "alice"


def test_is_grabbed_false_after_failed_grab():
    s = _session()
    # Roll high → miss
    s2, _ = _grab(s, attacker_ocv=8, target_dcv=10, attack_roll=18)
    is_g, by = Grab.is_grabbed(s2, "bob")
    assert is_g is False


# ---- Escape (STR contest, per 6E2 p67) ----

def test_escape_success_releases_grab():
    s = _session()
    s2, _ = _grab(s, attacker_ocv=10, target_dcv=5, attack_roll=10,
                  attacker_str=30, target_str=15)
    assert Grab.is_grabbed(s2, "bob")[0] is True
    s3, esc = Grab.escape(s2, escaper_id="bob", escaper_str=40, grabber_str=30)
    assert esc.success is True
    assert Grab.is_grabbed(s3, "bob") == (False, None)


def test_escape_failure_keeps_grab():
    s = _session()
    s2, _ = _grab(s, attacker_ocv=10, target_dcv=5, attack_roll=10,
                  attacker_str=30, target_str=15)
    s3, esc = Grab.escape(s2, escaper_id="bob", escaper_str=20, grabber_str=30)
    assert esc.success is False
    is_g, by = Grab.is_grabbed(s3, "bob")
    assert is_g is True
    assert by == "alice"


def test_escape_when_not_grabbed_raises():
    s = _session()
    with pytest.raises(ValueError, match="not grabbed"):
        Grab.escape(s, escaper_id="bob", escaper_str=20, grabber_str=30)


# ---- Throw (per 6E1 STR/THROWING TABLE) ----

def test_throw_damage_dc_is_str_over_5():
    """Damage is still STR/5 DCs (unchanged by Fix 10)."""
    out = Throw.compute(attacker_str=30)
    assert out.damage_dc == 6


def test_throw_max_distance_str_30_per_table():
    """Per 6E1 STR/THROWING TABLE (approximation): STR 30 → 40m for 1kg."""
    out = Throw.compute(attacker_str=30)
    assert out.max_distance_m == 40.0
    assert out.throw_distance_m == 40.0


def test_throw_max_distance_str_50_per_table():
    """Per 6E1 STR/THROWING TABLE: STR 50 → 64m for 1kg (was STR/5 = 10m)."""
    out = Throw.compute(attacker_str=50)
    assert out.max_distance_m == 64.0


def test_throw_max_distance_str_100_per_table():
    """Per 6E1 STR/THROWING TABLE: STR 100 → 144m (was STR/5 = 20m)."""
    out = Throw.compute(attacker_str=100)
    assert out.max_distance_m == 144.0


def test_throw_max_distance_str_5_per_table():
    """STR 5 → 8m (low end of table)."""
    out = Throw.compute(attacker_str=5)
    assert out.max_distance_m == 8.0


def test_throw_with_short_desired_distance_clamps_at_request():
    out = Throw.compute(attacker_str=50, desired_distance_m=4)
    assert out.max_distance_m == 64.0
    assert out.throw_distance_m == 4.0


def test_throw_excessive_distance_clamped_to_max():
    out = Throw.compute(attacker_str=20, desired_distance_m=999)
    assert out.max_distance_m == 32.0    # STR 20 → 32m
    assert out.throw_distance_m == 32.0


def test_throw_negative_distance_clamped_to_zero():
    out = Throw.compute(attacker_str=30, desired_distance_m=-5)
    assert out.throw_distance_m == 0.0


def test_throw_zero_str_yields_zero_damage_zero_distance():
    out = Throw.compute(attacker_str=0)
    assert out.damage_dc == 0
    assert out.max_distance_m == 0.0
    assert out.throw_distance_m == 0.0


def test_throw_phase_cost_half():
    out = Throw.compute(attacker_str=30)
    assert out.phase_cost == "half"


def test_throw_distance_uses_table_step_function():
    """STR 22 (between thresholds) uses the lower threshold's distance.

    The table jumps at STR 20 (32m) and STR 25 (32m); 22 should be 32m.
    """
    out = Throw.compute(attacker_str=22)
    assert out.max_distance_m == 32.0


def test_throw_str_above_100_extrapolates():
    """STR 120 → 144 + 16 = 160m (extrapolation per docstring)."""
    out = Throw.compute(attacker_str=120)
    assert out.max_distance_m == 160.0
