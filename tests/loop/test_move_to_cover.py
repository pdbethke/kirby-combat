"""Taking cover — the action nobody could choose.

NOBODY USED COVER BECAUSE NOBODY WAS EVER OFFERED IT. The engine gained
walls with `cover_level`, `compute_cover_level` to read them, and a Brief
that names them -- and no action that put a combatant behind one. The menu
had `move` (close on an enemy) and the reposition kinds (which need a
destination something else chose), so the only movement a chooser could
take was toward the shooting.

Measured on the O.K. Corral benchmark: four cover features on the page and
ZERO cover picks across three fights.

The parked consumer's driver HAD this (`_cover_move_actions`, with a
resolver beside it). It was left behind in the carve-out -- a regression
against what already existed, not new ground.
"""
from __future__ import annotations

import pytest

from conftest import fighter  # tests/loop/conftest.py
from kirby_combat.enumeration import ALL_ACTION_KINDS, enumerate_actions
from kirby_combat.loop import Roster, registered_kinds
from kirby_combat.loop.registry import UnresolvableAction, resolve_chosen
from kirby_combat.loop.run import distances_from
from kirby_combat.scene.cover import compute_cover_level
from kirby_combat.scene.placement import position_of
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Wall,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _scene(*, wall_x: float = 3.0, cover: int = 3, actor_at=(0.0, 0.0),
           enemy_at=(10.0, 0.0)) -> Scene:
    return Scene(
        id="s", name="A yard", bounds=SceneBounds(-30, -30, 0, 30, 30, 10),
        surfaces=[], hazards=[], ambient=AmbientConditions(),
        walls=[Wall(
            id="crates", name="Stack of crates",
            segment=(Position(wall_x, -2.0, 0.0), Position(wall_x, 2.0, 0.0)),
            height_m=1.4, blocks_los=False, blocks_movement=True,
            cover_level=cover, body=6, def_value=3,
        )],
        combatant_positions={
            "actor": Position(*actor_at, 0.0), "mark": Position(*enemy_at, 0.0),
        },
    )


def _session(scene: Scene):
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE, dice_roller=RandomRoller(seed=4),
        combatants=[
            fighter("actor", side=Side.named("a"), dex=20),
            fighter("mark", side=Side.named("b"), dex=15),
        ],
    ).start()


def _menu(session):
    actor = session.combatants["actor"]
    enemies = Roster(session).enemies_of(actor)
    return enumerate_actions(
        actor, enemies, has_scene=True, scene=session.scene,
        distances=distances_from(session.scene, actor, enemies),
    )


# ---- It is offered ----

def test_the_kind_is_declared_and_registered():
    assert "move_to_cover" in ALL_ACTION_KINDS
    assert "move_to_cover" in registered_kinds()


def test_cover_within_a_half_move_is_offered():
    """6E2 p.42: a Half Move leaves the actor an attack, which is why the
    offer says so."""
    offers = [a for a in _menu(_session(_scene())) if a.kind == "move_to_cover"]
    assert len(offers) == 1
    assert "Stack of crates" in offers[0].summary
    assert "cover 3/4" in offers[0].summary


def test_the_offer_quotes_the_penalty_attackers_will_take():
    """A number, not a rule -- the same lesson the OCV ladder taught."""
    offer = [a for a in _menu(_session(_scene())) if a.kind == "move_to_cover"][0]
    assert "OCV against you" in offer.summary
    # cover 3/4 is 75% covered, which 6E2 p.45 puts at -4.
    assert "-4 OCV" in offer.summary


def test_cover_beyond_a_half_move_is_not_offered():
    """Further off is a full Move and belongs to `reposition`."""
    far = _scene(wall_x=40.0)
    assert not [a for a in _menu(_session(far)) if a.kind == "move_to_cover"]


def test_a_feature_with_no_cover_is_not_offered():
    assert not [a for a in _menu(_session(_scene(cover=0))) if a.kind == "move_to_cover"]


def test_a_sceneless_fight_offers_no_cover():
    session = CombatSession.create(
        id="s", scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=4),
        combatants=[fighter("actor", side=Side.named("a")),
                    fighter("mark", side=Side.named("b"))],
    ).start()
    actor = session.combatants["actor"]
    assert not [
        a for a in enumerate_actions(actor, Roster(session).enemies_of(actor))
        if a.kind == "move_to_cover"
    ]


# ---- It works ----

def _take_cover(session):
    offer = [a for a in _menu(session) if a.kind == "move_to_cover"][0]
    return resolve_chosen(
        session, session.combatants["actor"], offer,
        template=TEMPLATE, roller=RandomRoller(seed=4),
    )


def test_taking_cover_moves_the_actor():
    session = _session(_scene())
    before = position_of(session.scene, "actor").x
    _take_cover(session)
    assert position_of(session.scene, "actor").x != before


def test_the_actor_ends_up_ON_THE_FAR_SIDE_of_the_cover():
    """WHICH SIDE IS THE WHOLE POINT. Standing on the enemy's side of a
    wall is not cover, it is a backstop."""
    session = _session(_scene(wall_x=3.0, enemy_at=(10.0, 0.0)))
    _take_cover(session)
    landed = position_of(session.scene, "actor")
    assert landed.x < 3.0, (
        f"landed at x={landed.x} -- the enemy is at x=10, so the wall must "
        f"be between them"
    )


def test_the_side_chosen_follows_the_threat():
    """Move the enemy to the other side and the actor goes the other way."""
    session = _session(_scene(wall_x=3.0, actor_at=(6.0, 0.0), enemy_at=(-8.0, 0.0)))
    _take_cover(session)
    assert position_of(session.scene, "actor").x > 3.0


def test_cover_you_would_have_to_walk_THROUGH_a_wall_to_reach_is_not_offered():
    """The covered side of a movement-blocking wall is on the far side of
    it, and you cannot walk through a wall to get there. Going round the
    end is a longer path than `movement_reach` finds, because it clamps
    toward the destination rather than pathfinding.

    The first version offered it anyway: the actor moved, stopped against
    the wall it could not cross, and finished the Phase no safer than it
    began. A tactics game would show no cover on that tile at all."""
    session = _session(_scene(wall_x=3.0, actor_at=(5.0, 0.0), enemy_at=(10.0, 0.0)))
    assert not [a for a in _menu(session) if a.kind == "move_to_cover"]


def test_it_actually_buys_cover():
    """Not just 'the actor moved' -- the rules must agree they are covered.

    The wall does not block movement here, so the covered side is
    reachable and the offer stands.
    """
    scene = _scene(wall_x=3.0, actor_at=(5.0, 0.0), enemy_at=(10.0, 0.0))
    object.__setattr__(scene.walls[0], "blocks_movement", False)
    session = _session(scene)
    enemy = position_of(session.scene, "mark")
    before = compute_cover_level(
        shooter_pos=enemy, target_pos=position_of(session.scene, "actor"),
        target_is_prone_or_diving=False, scene=session.scene,
    )
    _take_cover(session)
    after = compute_cover_level(
        shooter_pos=enemy, target_pos=position_of(session.scene, "actor"),
        target_is_prone_or_diving=False, scene=session.scene,
    )
    assert after > before, f"cover went {before} -> {after}"


def test_an_unknown_feature_refuses():
    from kirby_combat.enumeration import LegalAction

    session = _session(_scene())
    bogus = LegalAction(
        action_id="move_to_cover:no-such-wall", kind="move_to_cover",
        target_id=None, power_xmlid=None, power_name=None, summary="?",
    )
    with pytest.raises(UnresolvableAction, match="move_to_cover"):
        resolve_chosen(session, session.combatants["actor"], bogus,
                       template=TEMPLATE, roller=RandomRoller(seed=4))
