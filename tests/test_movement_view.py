"""movement_view lists every available mode with distances + END (movement spec §1).

Stubs mirror tests/test_reach.py: _Hero.characteristic_value reads a _cv dict;
_Pow carries xmlid/levels. No HDC needed.

END/NCM confirmed from movement class sources:
  running, leaping, flight, swimming: end_per_10m=1, noncombat_multiplier=4
  teleportation:                       end_per_10m=2, noncombat_multiplier=1
  tunneling:                           end_per_10m=1, noncombat_multiplier=1

_MOVE_M_PER_LEVEL=1.0 verified against a real character: FLIGHT LEVELS="15" → 15m flight
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
    """A combatant with all seven modes has all seven in movement_view().

    climbing added: 6E1 p70 makes it universal (every hero can climb ordinary
    things without the Skill), so it now always appears alongside the rest."""
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
    assert mode_names == {
        "running", "leaping", "flight", "teleportation", "swimming",
        "tunneling", "climbing",
    }


def test_leaping_vertical_is_half_combat():
    """Leaping vertical_m is always combat_m / 2 (6E rule)."""
    c = _combatant(cv={"RUNNING": 12, "LEAPING": 8})
    modes = {m.mode: m for m in c.movement_view()}
    assert modes["leaping"].vertical_m == 4.0


def test_vertical_zero_for_ground_modes():
    """Running and swimming have no vertical capability."""
    c = _combatant(
        cv={"RUNNING": 12, "LEAPING": 4},
        powers=[_Pow("SWIMMING", levels=10)],
    )
    modes = {m.mode: m for m in c.movement_view()}
    assert modes["running"].vertical_m == 0.0
    assert modes["swimming"].vertical_m == 0.0


def test_flight_vertical_equals_horizontal():
    """FLIGHT is full movement in any direction — vertical == combat_m, not 0."""
    c = _combatant(
        cv={"RUNNING": 12, "LEAPING": 4},
        powers=[_Pow("FLIGHT", levels=16)],
    )
    modes = {m.mode: m for m in c.movement_view()}
    assert modes["flight"].combat_m == 16.0
    assert modes["flight"].vertical_m == 16.0


def test_teleport_vertical_equals_range():
    """TELEPORTATION arrives anywhere in range, altitude included."""
    c = _combatant(
        cv={"RUNNING": 12, "LEAPING": 16},
        powers=[_Pow("TELEPORTATION", levels=30), _Pow("TELEPORTATION", levels=10)],
    )
    caps = [m for m in c.movement_view() if m.mode == "teleportation"]
    assert sorted(m.vertical_m for m in caps) == [10.0, 30.0]
    assert all(m.vertical_m == m.combat_m for m in caps)


def test_tunneling_vertical_equals_range():
    """TUNNELING moves through material in any direction, up included."""
    c = _combatant(
        cv={"RUNNING": 12, "LEAPING": 4},
        powers=[_Pow("TUNNELING", levels=8)],
    )
    modes = {m.mode: m for m in c.movement_view()}
    assert modes["tunneling"].vertical_m == 8.0


def test_every_mode_has_the_expected_vertical_fraction():
    """Pin the whole table so a refactor can't silently flatten any mode."""
    c = _combatant(
        cv={"RUNNING": 12, "LEAPING": 6},
        powers=[
            _Pow("FLIGHT", levels=20),
            _Pow("TELEPORTATION", levels=10),
            _Pow("SWIMMING", levels=5),
            _Pow("TUNNELING", levels=4),
        ],
    )
    modes = {m.mode: m for m in c.movement_view()}
    assert modes["running"].vertical_m == 0.0
    assert modes["leaping"].vertical_m == 3.0        # 6 / 2
    assert modes["flight"].vertical_m == 20.0
    assert modes["teleportation"].vertical_m == 10.0
    assert modes["swimming"].vertical_m == 0.0
    assert modes["tunneling"].vertical_m == 4.0


# --- the load-bearing one: vertical_m feeds the vantage search --------------

def test_flier_finds_a_vantage_over_a_wall_that_a_runner_cannot():
    """End-to-end: movement_view().vertical_m -> nearest_visible_point's
    vertical_reach. An 8m wall, too long to flank within either character's
    movement budget. The runner (leap 4 -> 2m vertical) finds nothing; the
    flier (16m -> 16m vertical) rises over the top. This is the teleporter /
    The symptom: with vertical_m hardcoded to 0 the flier got None too."""
    from kirby_combat.scene import (
        AmbientConditions, Position, Scene, SceneBounds, Wall,
    )
    from kirby_combat.scene.geometry import line_of_sight_clear
    from kirby_combat.scene.visibility import nearest_visible_point

    wall = Wall(
        id="w", name="Brick",
        segment=(Position(10, -100, 0.0), Position(10, 100, 0.0)),
        height_m=8.0, blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )
    scene = Scene(
        id="s", name="Arena",
        bounds=SceneBounds(-200, -200, -50, 200, 200, 50),
        surfaces=[], walls=[wall], hazards=[],
        ambient=AmbientConditions(), combatant_positions={},
    )
    obs, tgt = Position(0, 0, 1.5), Position(20, 0, 1.5)

    runner = _combatant(cv={"RUNNING": 12, "LEAPING": 4})
    r_modes = {m.mode: m for m in runner.movement_view()}
    r_best = None
    for m in r_modes.values():
        p = nearest_visible_point(obs, tgt, scene,
                                  radius=m.combat_m, vertical_reach=m.vertical_m)
        if p is not None:
            r_best = p
    assert r_best is None                       # wall too long to flank, too tall to leap

    flier = _combatant(cv={"RUNNING": 12, "LEAPING": 4},
                       powers=[_Pow("FLIGHT", levels=16)])
    f = {m.mode: m for m in flier.movement_view()}["flight"]
    p = nearest_visible_point(obs, tgt, scene,
                              radius=f.combat_m, vertical_reach=f.vertical_m)
    assert p is not None
    assert p.z > 8.0                            # above the wall top
    assert line_of_sight_clear(p, tgt, [wall]) is True


def test_power_derived_modes_carry_active_cost():
    """Pushing needs points-per-metre, and it must come from the cost
    engine rather than a constant in a consumer."""
    c = _combatant(
        cv={"RUNNING": 12, "LEAPING": 4},
        powers=[_Pow("TELEPORTATION", levels=15, active_cost=45.0)],
    )
    modes = {m.mode: m for m in c.movement_view()}
    tp = modes["teleportation"]
    assert tp.active_cost is not None
    assert tp.active_cost > 0
    # metres_per_point is what the push math divides out.
    assert tp.combat_m / tp.active_cost > 0


def test_characteristic_derived_modes_have_no_active_cost():
    """RUNNING/LEAPING are characteristics, not powers — there is no
    active_cost to read, and guessing one would be hand-rolled cost math."""
    c = _combatant(
        cv={"RUNNING": 12, "LEAPING": 4},
        powers=[_Pow("TELEPORTATION", levels=15, active_cost=45.0)],
    )
    modes = {m.mode: m for m in c.movement_view()}
    assert modes["running"].active_cost is None
    assert modes["leaping"].active_cost is None


def test_power_derived_mode_with_unusable_active_cost_becomes_none():
    """A bound-method or non-numeric active_cost must not leak through or
    be substituted with a default — it becomes None, an honest gap."""
    c = _combatant(
        cv={"RUNNING": 12, "LEAPING": 4},
        powers=[_Pow("FLIGHT", levels=20, active_cost=None)],
    )
    modes = {m.mode: m for m in c.movement_view()}
    assert modes["flight"].active_cost is None


def test_every_hero_can_climb():
    """6E1 p70: most characters can climb ordinary things without the Skill,
    so the MODE is universal. The Skill gates difficult faces, not the mode."""
    c = _combatant(powers=[_Pow("TELEPORTATION", levels=15)])
    caps = {m.mode: m for m in c.movement_view()}
    climb = caps["climbing"]
    assert climb.combat_m == 2.0          # 6E1 p70: base speed 2m per Phase
    assert climb.vertical_m == 2.0        # climbing IS vertical
    assert climb.noncombat_m == 2.0       # no noncombat sprint up a wall
    assert climb.end_per_10m == 1


def test_climbing_can_never_be_pushed():
    """No CLIMBING characteristic or power exists, so there is no active_cost
    to read — and inventing a metres-per-point constant is the forbidden thing."""
    c = _combatant(powers=[_Pow("TELEPORTATION", levels=15)])
    caps = {m.mode: m for m in c.movement_view()}
    assert caps["climbing"].active_cost is None


def test_teleporter_finds_a_vantage_over_the_same_wall():
    """A 30m teleport clears the same 8m wall the leap could not."""
    from kirby_combat.scene import (
        AmbientConditions, Position, Scene, SceneBounds, Wall,
    )
    from kirby_combat.scene.visibility import nearest_visible_point

    wall = Wall(
        id="w", name="Brick",
        segment=(Position(10, -100, 0.0), Position(10, 100, 0.0)),
        height_m=8.0, blocks_los=True, blocks_movement=True,
        cover_level=4, body=6,
    )
    scene = Scene(
        id="s", name="Arena",
        bounds=SceneBounds(-200, -200, -50, 200, 200, 50),
        surfaces=[], walls=[wall], hazards=[],
        ambient=AmbientConditions(), combatant_positions={},
    )
    obs, tgt = Position(0, 0, 1.5), Position(20, 0, 1.5)

    teleporter = _combatant(
        cv={"RUNNING": 12, "LEAPING": 16},
        powers=[_Pow("TELEPORTATION", levels=30)],
    )
    tp = {m.mode: m for m in teleporter.movement_view()}["teleportation"]
    assert tp.vertical_m == 30.0
    p = nearest_visible_point(obs, tgt, scene,
                              radius=tp.combat_m, vertical_reach=tp.vertical_m)
    assert p is not None
    assert p.z > 8.0
