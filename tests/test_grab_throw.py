"""Grab and Throw action tests."""
import pytest

from kirby_combat.models import Combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller
from kirby_combat.session import CombatSession
from kirby_combat.actions.grab import Grab, GrabResult
from kirby_combat.actions.throw import Throw, ThrowOutcome


def _c(id_: str, str_: int = 15) -> Combatant:
    return Combatant(
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


# ---- Grab declare ----

def test_grab_higher_str_wins():
    s = _session()
    s2, result = Grab.declare_and_resolve(s, attacker_id="alice", target_id="bob",
                                          attacker_str=30, target_str=15)
    assert isinstance(result, GrabResult)
    assert result.success is True
    assert result.attacker_id == "alice"
    assert result.target_id == "bob"


def test_grab_tied_str_fails_defender_wins():
    s = _session()
    s2, result = Grab.declare_and_resolve(s, attacker_id="alice", target_id="bob",
                                          attacker_str=20, target_str=20)
    assert result.success is False


def test_grab_lower_str_fails():
    s = _session()
    s2, result = Grab.declare_and_resolve(s, attacker_id="alice", target_id="bob",
                                          attacker_str=15, target_str=30)
    assert result.success is False


def test_grab_emits_action_declared_and_resolved_events():
    s = _session()
    s2, _ = Grab.declare_and_resolve(s, attacker_id="alice", target_id="bob",
                                     attacker_str=30, target_str=15)
    kinds = [e.kind for e in s2.event_log]
    # Should have SessionStarted + ActionDeclared + ActionResolved at minimum
    assert "ActionDeclared" in kinds
    assert "ActionResolved" in kinds
    # ActionDeclared comes before ActionResolved
    declared_ix = kinds.index("ActionDeclared")
    resolved_ix = kinds.index("ActionResolved")
    assert declared_ix < resolved_ix


# ---- is_grabbed ----

def test_is_grabbed_false_initially():
    s = _session()
    assert Grab.is_grabbed(s, "bob") == (False, None)


def test_is_grabbed_true_after_successful_grab():
    s = _session()
    s2, _ = Grab.declare_and_resolve(s, attacker_id="alice", target_id="bob",
                                     attacker_str=30, target_str=15)
    is_g, by = Grab.is_grabbed(s2, "bob")
    assert is_g is True
    assert by == "alice"


def test_is_grabbed_false_after_failed_grab():
    s = _session()
    s2, _ = Grab.declare_and_resolve(s, attacker_id="alice", target_id="bob",
                                     attacker_str=15, target_str=30)
    is_g, by = Grab.is_grabbed(s2, "bob")
    assert is_g is False


# ---- Escape ----

def test_escape_success_releases_grab():
    s = _session()
    s2, _ = Grab.declare_and_resolve(s, attacker_id="alice", target_id="bob",
                                     attacker_str=30, target_str=15)
    assert Grab.is_grabbed(s2, "bob")[0] is True
    s3, esc = Grab.escape(s2, escaper_id="bob", escaper_str=40, grabber_str=30)
    assert esc.success is True
    assert Grab.is_grabbed(s3, "bob") == (False, None)


def test_escape_failure_keeps_grab():
    s = _session()
    s2, _ = Grab.declare_and_resolve(s, attacker_id="alice", target_id="bob",
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


# ---- Throw ----

def test_throw_damage_dc_is_str_over_5():
    out = Throw.compute(attacker_str=30)
    assert out.damage_dc == 6


def test_throw_max_distance_is_str_over_5_meters():
    out = Throw.compute(attacker_str=30)
    assert out.max_distance_m == 6.0
    # default desired_distance is None → throws to max
    assert out.throw_distance_m == 6.0


def test_throw_with_short_desired_distance_clamps_at_request():
    out = Throw.compute(attacker_str=50, desired_distance_m=4)
    assert out.max_distance_m == 10.0
    assert out.throw_distance_m == 4.0


def test_throw_excessive_distance_clamped_to_max():
    out = Throw.compute(attacker_str=20, desired_distance_m=999)
    assert out.max_distance_m == 4.0
    assert out.throw_distance_m == 4.0


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
