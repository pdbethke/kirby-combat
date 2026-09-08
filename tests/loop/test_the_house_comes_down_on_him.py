"""The house comes down on Ike.

PeterB: "throw a wagon at a house that ike is hiding in and collapse it"
--- and then, when it collapsed and nobody was hurt: "add the damage when
the house collapses on ike".

THE DICE ARE THE BOOK'S. 6E2 p.142: "A character who falls 20m or less
takes 1d6 damage per full 2m fallen", physical Normal Damage. A structure
coming down on somebody is the same fall with the roles swapped --- the
mass falls the building's height --- so Fly's Studio at 5m is 2d6 and the
Harwood House at 6m is 3d6.

WHO IT LANDS ON IS OURS, and the book does not say: it covers a character
falling, not a building landing. Anyone within two metres of the wall's
footprint when it comes down, which is the ground a collapsing structure
occupies. Recorded as judgement.

It uses the ordinary damage path, so defenses apply. A brick standing in
the rubble of a shack he just knocked over should shrug it off, and he
does.
"""
from __future__ import annotations

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.collapse import collapse_damage_dice
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.scene.construct import Construct, constructs_in
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


# ---- the rule ----

def test_a_two_metre_wall_does_one_die():
    assert collapse_damage_dice(2.0) == 1


def test_flys_studio_at_five_metres_does_two():
    """1d6 per FULL 2m --- five metres is two dice, not two and a half."""
    assert collapse_damage_dice(5.0) == 2


def test_the_harwood_house_at_six_does_three():
    assert collapse_damage_dice(6.0) == 3


def test_something_waist_high_does_nothing():
    """A trough falling over is not a falling building."""
    assert collapse_damage_dice(1.5) == 0


# ---- and it lands on people ----

def _session(ike_at=(6.5, 7.5)):
    shack = Wall(id="shack", name="Fly's Studio",
                 segment=(Position(6.0, 6.0, 0.0), Position(6.0, 9.0, 0.0)),
                 height_m=6.0, blocks_los=True, blocks_movement=True,
                 cover_level=4, body=1, def_value=0)
    wagon = Construct(
        obj_id="wagon", kind="wall", portable=True,
        segment=(Position(2.0, 2.0, 0.0), Position(2.0, 2.0, 0.0)),
        height_m=1.5, blocks_los=False, blocks_movement=False,
        cover_level=2, def_value=3, body=6,
    )
    scene = Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 14.0, 14.0, 14.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (14, -2), (14, 14), (-2, 14)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[shack], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"lad": Position(2.0, 1.5, 0.0),
                             "ike": Position(*ike_at, 0.0)},
        constructs=[wagon],
    )
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE,
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter("lad", side=Side.solo("lad")),
                    fighter("ike", side=Side.named("cow"))],
    ).start()


def _throw_at_the_shack(session):
    actor = session.combatants["lad"]
    menu = enumerate_actions(
        actor, [session.combatants["ike"]], has_scene=True, scene=session.scene,
        constructs=constructs_in(session.scene) or None,
        movement=list(actor.movement_view()),
        actor_holding=True, held_construct_id="wagon",
    )
    offer = next(a for a in menu
                 if a.kind == "throw_object" and a.target_id == "shack")
    return resolve_chosen(session, actor, offer, template=TEMPLATE,
                          roller=RandomRoller(seed=5))


def test_the_man_beside_it_is_hurt_when_it_falls():
    session = _session(ike_at=(6.5, 7.5))
    before = session.combatants["ike"].state.current_stun
    resolved = _throw_at_the_shack(session)
    assert resolved.session.combatants["ike"].state.current_stun < before


def test_a_man_across_the_lot_is_not():
    """Two metres of footprint, not the whole yard."""
    session = _session(ike_at=(12.0, 12.0))
    before = session.combatants["ike"].state.current_stun
    resolved = _throw_at_the_shack(session)
    assert resolved.session.combatants["ike"].state.current_stun == before


def test_the_collapse_is_recorded():
    """A consumer reading the log should see the building come down and
    who it landed on, not just a wall going to 0 BODY."""
    resolved = _throw_at_the_shack(_session())
    payloads = [e.result_payload for e in resolved.events
                if getattr(e, "kind", "") == "ActionResolved"]
    assert any(p.get("collapsed_onto") for p in payloads), payloads
