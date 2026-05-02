"""Movement base + modes tests."""
import pytest

from fixtures.synthetic_hero import synthetic_combatant as Combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller
from kirby_combat.session import CombatSession
from kirby_combat.actions.movement.base import MovementAction


def _c(end: int = 30, max_end: int = 30) -> Combatant:
    return Combatant(
        id="alice", name="alice", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=max_end,
        current_stun=30, current_body=15, current_end=end,
    )


def _session(combatant: Combatant) -> CombatSession:
    return CombatSession.create(
        id="s1", combatants=[combatant], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


# ---- Mode factors ----

def test_half_move_full_dcv_full_ocv():
    m = MovementAction(name="running", distance_m=12, move_type="half", base_inches=12)
    assert m.dcv_factor() == 1.0
    assert m.ocv_factor() == 1.0


def test_full_move_half_dcv():
    m = MovementAction(name="running", distance_m=24, move_type="full", base_inches=12)
    assert m.dcv_factor() == 0.5
    assert m.ocv_factor() == 1.0


def test_noncombat_zero_ocv_and_dcv():
    m = MovementAction(name="running", distance_m=80, move_type="noncombat",
                       base_inches=12, noncombat_multiplier=4)
    assert m.dcv_factor() == 0
    assert m.ocv_factor() == 0


# ---- END cost ----

def test_end_cost_1_per_10m_rounded_up():
    assert MovementAction(name="running", distance_m=10, move_type="full",
                          base_inches=12).end_cost() == 1
    assert MovementAction(name="running", distance_m=15, move_type="full",
                          base_inches=12).end_cost() == 2     # 15/10 = 1.5 → 2
    assert MovementAction(name="running", distance_m=20, move_type="full",
                          base_inches=12).end_cost() == 2
    assert MovementAction(name="running", distance_m=21, move_type="full",
                          base_inches=12).end_cost() == 3     # 21/10 = 2.1 → 3


def test_end_cost_zero_for_zero_distance():
    assert MovementAction(name="running", distance_m=0, move_type="half",
                          base_inches=12).end_cost() == 0


def test_end_cost_uses_end_per_10m_override():
    # Some movement powers cost more than 1 END per 10m
    m = MovementAction(name="teleport", distance_m=20, move_type="full",
                       base_inches=20, end_per_10m=2)
    assert m.end_cost() == 4


# ---- Validate ----

def test_validate_half_move_within_capacity_returns_no_errors():
    c = _c(end=30)
    m = MovementAction(name="running", distance_m=12, move_type="half", base_inches=12)
    # half-move max = base_inches * 2m / 2 = 12 (each inch = 2m, half mode = 1/2 of inches)
    assert m.validate(c) == []


def test_validate_full_move_within_capacity():
    c = _c(end=30)
    m = MovementAction(name="running", distance_m=24, move_type="full", base_inches=12)
    # full-move max = base_inches * 2m = 24
    assert m.validate(c) == []


def test_validate_full_move_above_cap_raises_error():
    c = _c(end=30)
    m = MovementAction(name="running", distance_m=30, move_type="full", base_inches=12)
    errors = m.validate(c)
    assert len(errors) == 1
    assert "exceeds" in errors[0]


def test_validate_noncombat_uses_multiplier():
    c = _c(end=30)
    # noncombat max = base * 2 * noncombat_multiplier = 12 * 2 * 4 = 96m
    ok = MovementAction(name="running", distance_m=96, move_type="noncombat",
                        base_inches=12, noncombat_multiplier=4)
    assert ok.validate(c) == []
    too_far = MovementAction(name="running", distance_m=100, move_type="noncombat",
                             base_inches=12, noncombat_multiplier=4)
    errors = too_far.validate(c)
    assert any("exceeds" in e for e in errors)


def test_validate_insufficient_end_raises_error():
    c = _c(end=1)         # Only 1 END left
    m = MovementAction(name="running", distance_m=20, move_type="full", base_inches=12)
    # 20m / 10 = 2 END needed, only 1 available
    errors = m.validate(c)
    assert any("END" in e or "end" in e for e in errors)


def test_validate_unknown_move_type_raises_error():
    c = _c(end=30)
    m = MovementAction(name="running", distance_m=12, move_type="bogus", base_inches=12)
    errors = m.validate(c)
    assert any("move_type" in e for e in errors)


# ---- Resolve ----

def test_resolve_emits_movement_resolved_event():
    c = _c(end=30)
    s = _session(c)
    m = MovementAction(name="running", distance_m=20, move_type="full", base_inches=12)
    s2, evt = m.resolve(s, combatant_id="alice")
    assert evt.kind == "MovementResolved"
    assert evt.combatant_id == "alice"
    assert evt.move_type == "full"
    assert evt in s2.event_log


def test_resolve_decrements_combatant_current_end():
    c = _c(end=30)
    s = _session(c)
    m = MovementAction(name="running", distance_m=20, move_type="full", base_inches=12)
    s2, _ = m.resolve(s, combatant_id="alice")
    assert s2.combatants["alice"].current_end == 28      # 30 - 2 END for 20m


def test_resolve_records_velocity_in_event():
    """velocity_mps = distance moved this phase / segment duration. For now we
    set it equal to distance_m (the simple per-phase velocity); Phase 2.5 will
    refine when full SPD-segment timing wires in."""
    c = _c(end=30)
    s = _session(c)
    m = MovementAction(name="running", distance_m=20, move_type="full", base_inches=12)
    s2, evt = m.resolve(s, combatant_id="alice")
    assert evt.velocity_mps == 20.0


def test_resolve_raises_on_validation_failure():
    c = _c(end=1)
    s = _session(c)
    m = MovementAction(name="running", distance_m=30, move_type="full", base_inches=12)
    with pytest.raises(ValueError, match="movement validation failed"):
        m.resolve(s, combatant_id="alice")
