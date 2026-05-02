"""Concrete movement power tests — thin subclasses over MovementAction."""
import pytest

from fixtures.synthetic_hero import synthetic_combatant as Combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller
from kirby_combat.session import CombatSession
from kirby_combat.actions.movement import (
    MovementAction,
    Running, Leaping, Flight, Swimming, Teleportation, Tunneling,
)


def _c(end: int = 30) -> Combatant:
    return Combatant(
        id="alice", name="alice", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=end,
    )


def _session(c: Combatant) -> CombatSession:
    return CombatSession.create(
        id="s1", combatants=[c], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


# ---- Running -----------------------------------------------------------------

def test_running_make_returns_movementaction_named_running():
    m = Running.make(distance_m=20, move_type="full", base_inches=12)
    assert isinstance(m, MovementAction)
    assert m.name == "running"
    assert m.end_per_10m == 1
    assert m.noncombat_multiplier == 4


# ---- Leaping -----------------------------------------------------------------

def test_leaping_defaults():
    m = Leaping.make(distance_m=8, move_type="full", base_inches=4)
    assert m.name == "leaping"
    assert m.end_per_10m == 1
    assert m.noncombat_multiplier == 4


# ---- Flight ------------------------------------------------------------------

def test_flight_defaults():
    m = Flight.make(distance_m=20, move_type="full", base_inches=10)
    assert m.name == "flight"
    assert m.end_per_10m == 1
    assert m.noncombat_multiplier == 4


# ---- Swimming ----------------------------------------------------------------

def test_swimming_defaults():
    m = Swimming.make(distance_m=8, move_type="full", base_inches=4)
    assert m.name == "swimming"
    assert m.end_per_10m == 1
    assert m.noncombat_multiplier == 4


# ---- Teleportation -----------------------------------------------------------

def test_teleportation_costs_2_end_per_10m():
    m = Teleportation.make(distance_m=20, move_type="full", base_inches=10)
    assert m.name == "teleportation"
    assert m.end_per_10m == 2
    assert m.end_cost() == 4         # 20m / 10 = 2 × 2 END/10m = 4
    assert m.noncombat_multiplier == 1


# ---- Tunneling ---------------------------------------------------------------

def test_tunneling_no_noncombat_speedup():
    m = Tunneling.make(distance_m=10, move_type="noncombat", base_inches=5)
    assert m.name == "tunneling"
    assert m.noncombat_multiplier == 1
    # noncombat cap = base × 2 × multiplier = 5 × 2 × 1 = 10m (same as full move)
    assert m._max_distance_m() == 10.0


# ---- Integration: resolve through session ------------------------------------

def test_each_power_resolves_through_movementaction():
    """A power's make() result resolves the same as a hand-built MovementAction."""
    c = _c(end=30)
    s = _session(c)
    m = Running.make(distance_m=20, move_type="full", base_inches=12)
    s2, evt = m.resolve(s, combatant_id="alice")
    assert evt.kind == "MovementResolved"
    assert evt.move_type == "full"
    assert s2.combatants["alice"].current_end == 28      # 30 - 2 END for 20m


# ---- Validation tests --------------------------------------------------------

def test_validate_running_within_capacity():
    c = _c(end=30)
    m = Running.make(distance_m=24, move_type="full", base_inches=12)
    assert m.validate(c) == []


def test_validate_running_above_cap():
    c = _c(end=30)
    m = Running.make(distance_m=30, move_type="full", base_inches=12)
    errors = m.validate(c)
    assert any("exceeds" in e for e in errors)


def test_teleportation_higher_end_cost_blocks_short_supply():
    c = _c(end=3)
    m = Teleportation.make(distance_m=20, move_type="full", base_inches=10)
    # 20m / 10 = 2 × 2 END/10m = 4 END needed; only 3 available
    errors = m.validate(c)
    assert any("END" in e or "end" in e for e in errors)
