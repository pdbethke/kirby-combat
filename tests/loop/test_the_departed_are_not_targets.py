"""A man who has left the fight is not somebody you can shoot.

`Roster.standing` stopped counting a fighter who walked out the day
`disengage` was built, and `next_actor_id` stopped giving him Phases this
morning. But `enemies_of` and `allies_of` filter only on `is_down`, so
someone who LEFT was still on everybody's list --- still a target, still
an ally to shield, still counted when a side weighs the odds.

Measured at the O.K. Corral, and it is what the three-way stalemate
actually was. Doc Holliday broke off under the morale rule, walked to
(-7.5, 15.1) --- outside the lot --- and Power Lad spent the rest of the
fight choosing `move:doc_holliday`. `movement_reach` says that is not
reachable, so he stood at (5.5, 9.2) walking after a ghost while the last
Cowboy aimed at him, until the stalemate guard fired.

`Roster` already owns the answer (`has_left`, public since this morning).
These two just never asked it.
"""
from __future__ import annotations

from dataclasses import replace

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.loop import Roster
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


def _scene(**positions):
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 8.0, 12.0, 12.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (8, -2), (8, 12), (-2, 12)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={k: Position(*v) for k, v in positions.items()},
    )


def _roster(scene):
    session = CombatSession.create(
        id="s", scene=scene, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter("lad", side=Side.solo("lad")),
                    fighter("doc", side=Side.named("law")),
                    fighter("morgan", side=Side.named("law"))],
    ).start()
    return Roster(session), session


def test_a_man_who_walked_out_is_not_a_target():
    """Doc at (-7.5, 15.1): off the field, and gone."""
    roster, session = _roster(_scene(
        lad=(5.5, 9.2, 0.0), doc=(-7.5, 15.1, 0.0), morgan=(3.0, 6.0, 0.0)))
    ids = [e.id for e in roster.enemies_of(session.combatants["lad"])]
    assert "doc" not in ids
    assert "morgan" in ids, "the man still in the lot is still a target"


def test_a_man_who_walked_out_is_not_an_ally_either():
    """You cannot shield somebody who has gone home, and a side weighing
    the odds should not count him."""
    roster, session = _roster(_scene(
        lad=(5.5, 9.2, 0.0), doc=(-7.5, 15.1, 0.0), morgan=(3.0, 6.0, 0.0)))
    ids = [a.id for a in roster.allies_of(session.combatants["morgan"])]
    assert "doc" not in ids


def test_everyone_on_the_field_is_still_in_the_fight():
    """Guards the guard --- the ordinary case must not move."""
    roster, session = _roster(_scene(
        lad=(5.5, 9.2, 0.0), doc=(2.0, 4.0, 0.0), morgan=(3.0, 6.0, 0.0)))
    ids = [e.id for e in roster.enemies_of(session.combatants["lad"])]
    assert set(ids) == {"doc", "morgan"}


def test_a_fight_with_no_map_is_unaffected():
    """Most fights have no Scene at all, so nobody can have left one."""
    session = CombatSession.create(
        id="s", scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter("a", side=Side.named("x")),
                    fighter("b", side=Side.named("y"))],
    ).start()
    assert [e.id for e in Roster(session).enemies_of(session.combatants["a"])] == ["b"]
