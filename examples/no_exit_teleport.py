"""Cannot Be Escaped With Teleportation — 6E1 p220 (Entangle) / p175 (Barrier).

Teleportation is the one escape hatch an Entangle leaves open (6E1 p217: it
stops every Movement Power EXCEPT Teleportation; p218 lists Teleporting out
among the escape routes) and the normal way out of an englobing Barrier. The
+1/4 Advantage "Cannot Be Escaped With Teleportation" (XMLID NOTELEPORT)
closes that hatch -- unless the escaper's Teleportation is Armor Piercing,
which cancels the Advantage level for level; both sides may stack levels
(all paraphrased; this project ships no rules text -- open your own copy).

Demonstrates: `noteleport_levels`, `armor_piercing_levels`,
`can_teleport_escape`, and the `movement_reach` teleport gate over a
NOTELEPORT barrier construct.
"""
from kirby_combat import (
    armor_piercing_levels, can_teleport_escape, noteleport_levels,
)
from kirby_combat.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)
from kirby_combat.scene.construct import Construct
from kirby_combat.scene.movement_legality import movement_reach


class _Stub:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def power(xmlid, mods=()):
    return _Stub(xmlid=xmlid, assigned_modifiers=[
        _Stub(xmlid=x, levels=lv) for x, lv in mods])


# -- the rule, on powers ----------------------------------------------------
sticky_web = power("ENTANGLE", [("NOTELEPORT", 2)])   # "(x2; +1/2)" shape
plain_net = power("ENTANGLE")
blink = power("TELEPORTATION")
phase_blink = power("TELEPORTATION", [("ARMORPIERCING", 2)])

assert noteleport_levels(sticky_web) == 2
assert noteleport_levels(plain_net) == 0
assert armor_piercing_levels(phase_blink) == 2

assert can_teleport_escape(plain_net, blink)          # 6E1 p218: works normally
assert not can_teleport_escape(sticky_web, blink)     # 6E1 p220: blocked
assert can_teleport_escape(sticky_web, phase_blink)   # AP 2 cancels x2

# -- the same rule, on the map (6E1 p175: an englobing Barrier) -------------
scene = Scene(
    id="cell", name="No Exit",
    bounds=SceneBounds(0, 0, 0, 20, 20, 20),
    surfaces=[Surface(id="ground", name="Ground",
                      polygon_xy=[(0, 0), (20, 0), (20, 20), (0, 20)],
                      elevation_m=0.0, surface_type="ground",
                      cover_level=0, is_supporting=True)],
    walls=[], hazards=[], ambient=AmbientConditions(),
    combatant_positions={},
)
scene.constructs = [Construct(
    obj_id="cage", kind="force_wall",
    segment=(Position(8, 0, 0), Position(8, 20, 0)), height_m=8.0,
    blocks_los=True, blocks_movement=True, permeability="impermeable",
    no_teleport_levels=1,
)]

inside, outside = Position(2, 10, 0), Position(15, 10, 0)
blocked = movement_reach("teleportation", inside, outside, 20.0, scene)
assert blocked.reachable is False                     # the blink is refused
freed = movement_reach("teleportation", inside, outside, 20.0, scene,
                       teleport_ap_levels=1)
assert freed.reachable is True                        # AP meets the levels

# -- breakout margins (6E2 p126) and STR dice (6E1 p134) --------------------
from kirby_combat import breakout, stacked_entangle, str_escape_dice

assert breakout(8, 4).action_regained == "full"     # 2x remaining: full Phase
assert breakout(4, 4).action_regained == "half"
assert not breakout(3, 4).escaped
assert stacked_entangle(6, 4, 4, 3, 2, 5) == (7, 4, 5)   # highest +1; highest defs
assert str_escape_dice(30) == 6 and str_escape_dice(30, casual=True) == 3

# -- END and default defenses (6E2 p41; 6E1 p217) ---------------------------
from kirby_combat import entangle_default_defenses, str_escape_end_cost

assert str_escape_end_cost(30) == 3                 # 1 END per 10 STR used
assert str_escape_end_cost(30, casual=True) == 1    # pays for the half used
assert entangle_default_defenses(6) == (6, 6)       # 1 PD + 1 ED per 1d6

print("no_exit_teleport: NOTELEPORT blocks the blink; Armor Piercing cancels it.")
