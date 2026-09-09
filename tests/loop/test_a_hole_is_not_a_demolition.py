"""Shoot a hole in a wall. Do not knock the building over.

PeterB: "you cannot actually shoot down an entire saloon", then "fix the
wall scale so a pistol cant level a building", then --- the part that
makes this a feature and not just a guard --- "yes but he could shoot
through a hole. thats a legit genre tactic".

WHAT WAS WRONG. Every destroyed construct went to `bring_it_down`: the
whole thing left the board and dropped its full height in dice on anyone
nearby. A wall face and a building were the same object, so putting a
hole through the west wall of the Harwood House levelled the Harwood
House. Four pistol shots.

THE BOOK ALREADY SAYS A WALL IS SMALL. 6E2 p.173's Objects Table: a
Wooden wall is PD 4 / ED 3 / BODY 3, a Home outside wall PD 4 / ED 6 /
BODY 3, a Brick wall PD 5 / ED 10 / BODY 3. Ours were BODY 8. And p.172's
own worked example says what that BODY buys --- Chiron chops a 5 PD, 6
BODY wall, takes 5 through, and it is "damaged but still standing;
another good blow will cut THROUGH it easily". Cutting through a wall is
a HOLE. The book is not describing a demolition and never was.

SO THERE ARE THREE THINGS, and the engine had one.

  a barrel      SMASHES  --- destroyed, gone, nothing falls on anybody
  a wall face   BREACHES --- a hole: you can see and SHOOT through it,
                            you cannot walk through it, and the building
                            it belongs to is still standing
  a building    COLLAPSES --- the existing rule, and the only one that
                            drops dice on the people underneath

`Wall.part_of` names the structure a face belongs to, because nothing else
in the data could tell a boarding-house wall from a stack of whiskey
barrels: both are `Wall`, both block, both have BODY.

A BULLET HOLE IS NOT A DOORWAY. A breached wall stops blocking line of
sight and keeps blocking movement.

AND YOU SHOOT THROUGH IT AT A PENALTY. PeterB: "at a substantial ocv
penalty due to the size of the hole". That is the cover rules, not a new
number --- the breached wall still covers most of the man behind it, so
it lands on cover level 3, which `cover_ocv_modifier` prices at -4 under
6E2 p.45's Behind Cover Modifiers: "full cover except head/torso", which
is exactly what a man seen through a hole in a wall is.

This is `smash_cover` made correct rather than absurd: shoot the cover to
open a firing line, which is the genre tactic, instead of demolishing a
boarding house with a revolver.
"""
from __future__ import annotations

from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.collapse import bring_it_down, is_structure
from kirby_combat.scene.construct import Construct
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


def _wall(**kw):
    base = dict(
        id="harwood", name="Harwood House (west wall)",
        segment=(Position(0.0, 0.0, 0.0), Position(0.0, 10.0, 0.0)),
        height_m=6.0, blocks_los=True, blocks_movement=True,
        cover_level=4, body=3, def_value=4,
    )
    base.update(kw)
    return Wall(**base)


def _building():
    return Construct(
        obj_id="harwood-interior", kind="wall",
        segment=(Position(0.0, 0.0, 0.0), Position(0.0, 10.0, 0.0)),
        polygon_xy=[(-2.0, 0.0), (0.0, 0.0), (0.0, 10.0), (-2.0, 10.0)],
        elevation_range_m=(0.0, 6.0), height_m=6.0,
        blocks_los=True, blocks_movement=True,
        cover_level=4, def_value=8, body=30,
    )


def _session(walls, constructs=(), **positions):
    scene = Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-4.0, -2.0, 0.0, 14.0, 14.0, 14.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-4, -2), (14, -2), (14, 14), (-4, 14)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=list(walls), constructs=list(constructs), hazards=[],
        ambient=AmbientConditions(light_level=4),
        combatant_positions={k: Position(*v, 0.0) for k, v in positions.items()},
    )
    return CombatSession.create(
        id="s", scene=scene, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter("tom", side=Side.named("cow")),
                    fighter("ike", side=Side.named("law"))],
    ).start()


def _wall_named(session, wall_id):
    return next((w for w in session.scene.walls if w.id == wall_id), None)


# ---- What is what ----

def test_a_thing_with_a_footprint_is_a_building():
    assert is_structure(_building()) is True


def test_a_bare_segment_is_not():
    """A wall face, and a stack of barrels, are both just a line."""
    assert is_structure(_wall()) is False


# ---- A hole ----

def test_breaching_a_wall_leaves_the_building_standing():
    """The whole point. Ike is inside Harwood House; the west wall is
    holed and nothing lands on him."""
    session = _session([_wall(part_of="harwood-interior")], [_building()],
                       tom=(2.0, 5.0), ike=(-1.0, 5.0))
    session, caught = bring_it_down(
        session, _wall_named(session, "harwood"),
        roller=RandomRoller(seed=5),
        template=CombatTemplate.default_6e_superheroic(),
    )
    assert caught == [], "a hole in a wall falls on nobody"


def test_you_can_shoot_through_the_hole():
    """PeterB's genre tactic. The wall stays on the board and stops
    blocking line of sight."""
    session = _session([_wall(part_of="harwood-interior")], [_building()],
                       tom=(2.0, 5.0), ike=(-1.0, 5.0))
    session, _ = bring_it_down(
        session, _wall_named(session, "harwood"),
        roller=RandomRoller(seed=5),
        template=CombatTemplate.default_6e_superheroic(),
    )
    holed = _wall_named(session, "harwood")
    assert holed is not None, "a breached wall is still there"
    assert holed.blocks_los is False


def test_but_you_cannot_walk_through_it():
    """A bullet hole is not a doorway."""
    session = _session([_wall(part_of="harwood-interior")], [_building()],
                       tom=(2.0, 5.0), ike=(-1.0, 5.0))
    session, _ = bring_it_down(
        session, _wall_named(session, "harwood"),
        roller=RandomRoller(seed=5),
        template=CombatTemplate.default_6e_superheroic(),
    )
    assert _wall_named(session, "harwood").blocks_movement is True


def test_shooting_through_the_hole_costs_you():
    """A substantial OCV penalty, taken from the book's cover table rather
    than invented: the hole leaves the man mostly covered."""
    session = _session([_wall(part_of="harwood-interior")], [_building()],
                       tom=(2.0, 5.0), ike=(-1.0, 5.0))
    session, _ = bring_it_down(
        session, _wall_named(session, "harwood"),
        roller=RandomRoller(seed=5),
        template=CombatTemplate.default_6e_superheroic(),
    )
    from kirby_combat.scene.cover import cover_ocv_modifier

    holed = _wall_named(session, "harwood")
    assert 0 < holed.cover_level < 4
    assert cover_ocv_modifier(holed.cover_level * 25) <= -4


# ---- A smash ----

def test_a_barrel_is_simply_gone():
    """No `part_of`, no footprint: nothing to breach and nothing to drop.

    And it LEAVES. At 1.2m the barrels do no collapse damage, and that
    branch used to return before taking them off the board -- so a smashed
    stack went on granting cover and turning movement back for the rest of
    the fight, which is exactly the defect `_off_the_board` exists to
    prevent, surviving in the one path that skipped it.
    """
    barrels = _wall(id="barrels", name="Stack of whiskey barrels",
                    height_m=1.2, cover_level=2, body=4, def_value=2,
                    blocks_los=False)
    session = _session([barrels], [], tom=(6.0, 5.0), ike=(-1.0, 5.0))
    session, caught = bring_it_down(
        session, _wall_named(session, "barrels"),
        roller=RandomRoller(seed=5),
        template=CombatTemplate.default_6e_superheroic(),
    )
    assert _wall_named(session, "barrels") is None
    assert caught == []


# ---- A collapse, which still works ----

def test_a_building_still_comes_down_on_the_man_inside():
    """The rule PeterB asked for is untouched: destroy the STRUCTURE and
    it lands on whoever is under it."""
    # Tom stands well clear; Ike is inside the footprint.
    session = _session([], [_building()], tom=(6.0, 5.0), ike=(-1.0, 5.0))
    before = session.combatants["ike"].state.current_stun
    session, caught = bring_it_down(
        session, _building(), roller=RandomRoller(seed=5),
        template=CombatTemplate.default_6e_superheroic(),
    )
    assert [c["combatant_id"] for c in caught] == ["ike"]
    assert session.combatants["ike"].state.current_stun < before
