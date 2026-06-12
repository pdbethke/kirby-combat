"""movement_view lists every available mode with distances + END (movement spec §1).

Stubs mirror tests/test_reach.py: _Hero.characteristic_value reads a _cv dict;
_Pow carries xmlid/levels. No HDC needed.

END/NCM confirmed from movement class sources:
  running, leaping, flight, swimming: end_per_10m=1, noncombat_multiplier=4
  teleportation:                       end_per_10m=2, noncombat_multiplier=1
  tunneling:                           end_per_10m=1, noncombat_multiplier=1

_MOVE_M_PER_LEVEL=1.0 verified against Gyre.hdc: FLIGHT LEVELS="15" → 15m flight
(characteristic_value("FLIGHT") returns 0.0 — FLIGHT is a power, not a characteristic).
RUNNING/LEAPING come straight from characteristic_value() which returns metres.
"""
from dataclasses import dataclass, field

from kirby_combat.hero_view import HeroCombatant, HeroCombatState


@dataclass
class _Pow:
    xmlid: str
    name: str = ""
    levels: int = 0
    level_value: float = 1.0
    base_cost: float = 0.0
    active_cost: float | None = None
    assigned_modifiers: list = field(default_factory=list)
    sub_powers: list = field(default_factory=list)


@dataclass
class _Hero:
    name: str = "T"
    template_name: str = "synthetic.T.hdt"
    powers: list = field(default_factory=list)
    _cv: dict = field(default_factory=dict)

    def characteristic_value(self, xmlid: str) -> float:
        return float(self._cv.get(xmlid.upper(), 0))


def _combatant(*, powers=None, cv=None):
    base = {
        "STR": 20, "DEX": 13, "OCV": 7, "DCV": 7,
        "RUNNING": 12, "LEAPING": 4, "STUN": 30, "BODY": 12, "END": 40,
        "OMCV": 3, "DMCV": 3, "SPD": 3, "EGO": 11,
        "CON": 15, "PRE": 10, "REC": 5,
    }
    base.update(cv or {})
    hero = _Hero(powers=powers or [], _cv=base)
    return HeroCombatant(
        id="t",
        hero=hero,
        state=HeroCombatState(current_stun=30, current_body=12, current_end=40),
        knockback_resistance=0,
    )


def test_running_and_leaping_from_characteristics():
    """Running + leaping come from characteristic_value; no movement powers needed."""
    c = _combatant(cv={"RUNNING": 12, "LEAPING": 4, "STR": 20})
    modes = {m.mode: m for m in c.movement_view()}
    assert "running" in modes
    assert modes["running"].combat_m == 12.0
    assert modes["running"].end_per_10m == 1
    assert modes["running"].noncombat_m == 48.0  # 12 * 4 (NCM)
    assert "leaping" in modes
    assert modes["leaping"].combat_m == 4.0
    assert modes["leaping"].vertical_m == 2.0    # vertical = half horizontal (6E)
    assert modes["leaping"].end_per_10m == 1
    assert "flight" not in modes                 # no FLIGHT power


def test_flight_teleport_from_powers():
    """FLIGHT and TELEPORTATION are powers; levels map 1:1 to metres."""
    c = _combatant(
        cv={"RUNNING": 12, "LEAPING": 4},
        powers=[_Pow("FLIGHT", levels=20), _Pow("TELEPORTATION", levels=15)],
    )
    modes = {m.mode: m for m in c.movement_view()}
    # Flight: 1 END/10m, NCM 4×
    assert "flight" in modes
    assert modes["flight"].combat_m == 20.0
    assert modes["flight"].noncombat_m == 80.0   # 20 * 4
    assert modes["flight"].end_per_10m == 1
    # Teleportation: 2 END/10m, NCM 1× (teleport doesn't scale noncombat)
    assert "teleportation" in modes
    assert modes["teleportation"].combat_m == 15.0
    assert modes["teleportation"].noncombat_m == 15.0  # 15 * 1
    assert modes["teleportation"].end_per_10m == 2


def test_swimming_tunneling_from_powers():
    """SWIMMING and TUNNELING as powers show up correctly."""
    c = _combatant(
        cv={"RUNNING": 12, "LEAPING": 4},
        powers=[_Pow("SWIMMING", levels=10), _Pow("TUNNELING", levels=8)],
    )
    modes = {m.mode: m for m in c.movement_view()}
    # Swimming: 1 END/10m, NCM 4×
    assert "swimming" in modes
    assert modes["swimming"].combat_m == 10.0
    assert modes["swimming"].noncombat_m == 40.0
    assert modes["swimming"].end_per_10m == 1
    # Tunneling: 1 END/10m, NCM 1× (noncombat speedup doesn't apply)
    assert "tunneling" in modes
    assert modes["tunneling"].combat_m == 8.0
    assert modes["tunneling"].noncombat_m == 8.0   # 8 * 1
    assert modes["tunneling"].end_per_10m == 1


def test_no_zero_distance_modes():
    """Modes with combat_m == 0 are not emitted."""
    c = _combatant(cv={"RUNNING": 12, "LEAPING": 0})
    mode_names = {m.mode for m in c.movement_view()}
    assert "leaping" not in mode_names             # 0 leaping → no leaping entry
    assert "running" in mode_names                 # RUNNING still present


def test_all_modes_present_for_full_mover():
    """A combatant with all six modes has all six in movement_view()."""
    c = _combatant(
        cv={"RUNNING": 12, "LEAPING": 6},
        powers=[
            _Pow("FLIGHT", levels=20),
            _Pow("TELEPORTATION", levels=10),
            _Pow("SWIMMING", levels=5),
            _Pow("TUNNELING", levels=4),
        ],
    )
    mode_names = {m.mode for m in c.movement_view()}
    assert mode_names == {"running", "leaping", "flight", "teleportation", "swimming", "tunneling"}


def test_leaping_vertical_is_half_combat():
    """Leaping vertical_m is always combat_m / 2 (6E rule)."""
    c = _combatant(cv={"RUNNING": 12, "LEAPING": 8})
    modes = {m.mode: m for m in c.movement_view()}
    assert modes["leaping"].vertical_m == 4.0


def test_vertical_zero_for_non_leaping_modes():
    """Only leaping gets a non-zero vertical_m; all others are 0.0."""
    c = _combatant(
        cv={"RUNNING": 12, "LEAPING": 4},
        powers=[_Pow("FLIGHT", levels=15)],
    )
    modes = {m.mode: m for m in c.movement_view()}
    assert modes["running"].vertical_m == 0.0
    assert modes["flight"].vertical_m == 0.0
