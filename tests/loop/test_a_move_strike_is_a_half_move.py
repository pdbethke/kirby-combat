"""Close and strike, and you only get HALF your movement to do it.

6E2 p.26 draws the line by distance, not by intent: "A Full Move is
defined as moving more than half of a character's movement distance with
a particular mode of movement. It takes a Full Phase Action to make a
Full Move; a character who has made a Full Move can't perform any other
Action in that Phase. A Half Move is defined as moving up to half of a
character's movement distance ... A character who's made a Half Move can
perform another Half Phase Action in that Phase."

`enumeration._melee_gate` already applies it perfectly, offering a
`move_strike` only when `half_move_m >= verdict.shortfall_m`. Two things
in the RESOLVER then throw that away:

  * it hands `move_toward` the FULL combat move as the allowance
    (`_move_capacity`), where the sibling resolvers two hundred lines
    down correctly ask `_half_move` and `_full_move`; and
  * it sets the destination to the target's EXACT POSITION rather than to
    a point within reach of them, so a closing fighter walks the whole
    distance and ends up standing in the same spot as the man he hit.

Between them, an attacker seven metres from his enemy makes a seven-metre
move -- a Full Move on a Running 12 character -- and then attacks anyway.

The gate being right in one module and ignored in the other is the same
shape as the range penalty: the rule was computed, correct, and delivered
nowhere.
"""
from __future__ import annotations

import math

import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.loop.run import distances_from
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _closing_on(apart_m: float):
    scene = Scene(
        id="f", name="f", bounds=SceneBounds(-50, -50, 0.0, 50, 50, 10.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-50, -50), (50, -50), (50, 50), (-50, 50)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"a": Position(0.0, 0.0, 0.0),
                             "b": Position(apart_m, 0.0, 0.0)},
    )
    session = CombatSession.create(
        id="s", scene=scene, template=TEMPLATE, dice_roller=RandomRoller(seed=2),
        combatants=[fighter("a", side=Side.named("x")),
                    fighter("b", side=Side.named("y"))],
    ).start()
    actor = session.combatants["a"]
    enemy = session.combatants["b"]
    menu = enumerate_actions(
        actor, [enemy], has_scene=True, scene=session.scene,
        distances=distances_from(session.scene, actor, [enemy]),
    )
    return session, actor, [m for m in menu if m.kind == "move_strike"]


def _half_move_of(actor) -> float:
    return float(actor.hero.characteristic_value("RUNNING")) / 2.0


def test_closing_and_striking_never_costs_more_than_half_a_move():
    """The distance actually covered, measured off the Scene."""
    session, actor, offers = _closing_on(7.0)
    assert offers, "a seven-metre gap is inside a Half Move plus reach"

    resolved = resolve_chosen(session, actor, offers[0],
                              template=TEMPLATE, roller=RandomRoller(seed=2))
    landing = resolved.session.scene.combatant_positions["a"]
    covered = math.dist((0.0, 0.0, 0.0), (landing.x, landing.y, landing.z))

    assert covered <= _half_move_of(actor) + 1e-6, (
        f"closed {covered:.2f}m to strike, which is more than the "
        f"{_half_move_of(actor):.1f}m a Half Move allows (6E2 p.26)"
    )


def test_a_closing_fighter_stops_short_of_standing_on_his_enemy():
    """`reposition_dest` is the enemy's own position, so nothing stopped
    the mover from ending the Phase inside him."""
    session, actor, offers = _closing_on(7.0)
    resolved = resolve_chosen(session, actor, offers[0],
                              template=TEMPLATE, roller=RandomRoller(seed=2))
    positions = resolved.session.scene.combatant_positions
    gap = math.dist(
        (positions["a"].x, positions["a"].y, positions["a"].z),
        (positions["b"].x, positions["b"].y, positions["b"].z),
    )
    assert gap > 0.0, "the attacker finished the Phase standing in his target"
