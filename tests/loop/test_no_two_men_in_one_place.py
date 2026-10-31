"""Two men do not end a move on one spot.

The book has no general rule against sharing a space, but it never puts
two bodies at one point. 6E2 p.56: Hand-To-Hand Combat "is combat between
two characters who are within Reach of one another", and Reach is "1 meter
around himself"; so men in contact, grappling included, stand up to a
metre apart. 6E2 p.31: Teleporting onto an occupied point is a mishap, and
into a solid object "his natural safety system kicks in, getting him to the
closest space from the target point where he fits". Running into a man on
purpose is a Move Through (p.72), an attack.

The engine set a man's own position as the destination of a move toward
him, so a closing fighter finished standing on the man he closed on, and
one coming back onto the board landed on whoever stood at the edge.

PETER'S RULING (2026-10-31), from those pages:
1. A move toward a man stops within the mover's Reach of him.
2. No move ends within `placement.PERSONAL_SPACE_M` (1m, base Reach) of
   another combatant: it ends at the nearest free spot short of it, as
   p.31's safety system does, without the damage.
"""
from __future__ import annotations

from kirby_dice import FakeRoller
from kirby_world.geometry import distance_3d
from kirby_world.scene import AmbientConditions, Position, Scene, SceneBounds, Surface

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.placement import PERSONAL_SPACE_M, move_toward
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import RAW_HEROIC


def _scene(**positions):
    return Scene(
        id="lot", name="A Lot", bounds=SceneBounds(0, 0, 0, 100, 100, 50),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(0, 0), (100, 0), (100, 100), (0, 100)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(gravity_scale=1.0),
        combatant_positions={k: Position(*v) for k, v in positions.items()},
    )


def _session(**positions):
    men = [synthetic_combatant(id="r", name="r", spd=4, dex=20, running=40,
                               max_end=40, side=Side.named("a")),
           synthetic_combatant(id="e", name="e", spd=4, side=Side.named("b"))]
    if "o" in positions:
        men.append(synthetic_combatant(id="o", name="o", spd=4, side=Side.named("b")))
    return CombatSession.create(id="s", combatants=men, scene=_scene(**positions),
                                template=RAW_HEROIC, dice_roller=FakeRoller([])).start()


def _where(session, cid):
    return session.scene.combatant_positions[cid]


def _move_at(kind="move"):
    return LegalAction(action_id=f"{kind}:e", kind=kind, target_id="e",
                       power_xmlid=None, power_name=None, mode="running",
                       summary="close on e")


def test_closing_on_a_man_stops_within_reach_of_him():
    """20m away on Running 40: he used to walk the whole gap and stand on e."""
    s = _session(r=(10, 10, 0), e=(30, 10, 0))
    out = resolve_chosen(s, s.combatants["r"], _move_at(), template=RAW_HEROIC,
                         roller=FakeRoller([]))
    gap = distance_3d(_where(out.session, "r"), _where(out.session, "e"))
    assert abs(gap - 1.0) < 1e-6, gap


def test_a_half_move_toward_him_stops_within_reach_too():
    s = _session(r=(10, 10, 0), e=(25, 10, 0))
    out = resolve_chosen(s, s.combatants["r"], _move_at("half_move"),
                         template=RAW_HEROIC, roller=FakeRoller([]))
    gap = distance_3d(_where(out.session, "r"), _where(out.session, "e"))
    assert abs(gap - 1.0) < 1e-6, gap


def test_a_man_already_within_reach_does_not_walk_onto_him():
    s = _session(r=(10, 10, 0), e=(10.8, 10, 0))
    moved, _ = move_toward(s, "r", Position(10.8, 10, 0), mode="running",
                           distance_m=40, template=RAW_HEROIC)
    assert _where(moved, "r") == Position(10, 10, 0), "he stays where he is"


def test_a_move_to_where_somebody_stands_ends_short_of_him():
    """The point is a destination, not a man (a cover spot, a vantage):
    somebody else is standing on it."""
    s = _session(r=(10, 10, 0), e=(80, 80, 0), o=(30, 10, 0))
    moved, _ = move_toward(s, "r", Position(30, 10, 0), mode="running",
                           distance_m=40, template=RAW_HEROIC)
    here = _where(moved, "r")
    assert abs(distance_3d(here, _where(moved, "o")) - PERSONAL_SPACE_M) < 1e-6
    assert here.x < 30, "short of him, on the way in"
