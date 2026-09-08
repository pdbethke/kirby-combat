"""Do not offer a man cover he is already behind.

`fight_from_cover` plans two steps: move to cover, THEN shoot from it.
`TacticChooser` reads `plan.steps[0]` and nothing else, so a two-step
plan degenerates into its first step repeated forever. Measured on the
O.K. Corral: Tom McLaury took cover in three consecutive Phases and never
fired; Frank McLaury twice; the Earps went untouched through the whole
fight because the men shooting at them had all gone to ground and stayed
there.

The fix is not to teach the chooser to advance through steps --- a plan
step is advice, and which step applies depends on the state the actor is
actually in. It is for the MENU to stop offering something that changes
nothing. "Take cover behind the barrels" is not an action when you are
already behind the barrels; it is a no-op wearing an action's name, and
offering it invites exactly the loop that was measured.

So a cover spot is offered only when it BEATS the cover the actor has
where they stand. Once behind the barrels, the offer is gone, the tactic
falls through to `sustained_fire`, and the man shoots --- which is what
"take cover and fire from safety" meant all along.
"""
from __future__ import annotations

import pytest

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _scene(actor_at):
    """A barrel at x=5, the enemy away at x=0."""
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-20.0, -20.0, 0.0, 20.0, 20.0, 10.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-20, -20), (20, -20), (20, 20), (-20, 20)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[Wall(id="barrel", name="Barrel",
                    segment=(Position(5.0, -1.5, 0.0), Position(5.0, 1.5, 0.0)),
                    height_m=1.2, blocks_los=False, blocks_movement=True,
                    cover_level=2, body=4, def_value=2, climb_difficulty=0)],
        hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"actor": Position(*actor_at, 0.0),
                             "mark": Position(0.0, 0.0, 0.0)},
    )


def _menu(actor_at):
    session = CombatSession.create(
        id="s", scene=_scene(actor_at), template=TEMPLATE,
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter("actor", side=Side.named("a"), dex=20),
                    fighter("mark", side=Side.named("b"), dex=10)],
    ).start()
    actor = session.combatants["actor"]
    return enumerate_actions(
        actor, [session.combatants["mark"]], scene=session.scene,
        has_scene=True, movement=list(actor.movement_view()),
    )


def _cover_offers(menu):
    return [a for a in menu if a.kind == "move_to_cover"]


def test_a_man_in_the_open_is_offered_the_barrel():
    """The baseline: OFF the line between the enemy and the barrel, so
    nothing shields him where he stands, and the offer is worth making.

    Two ways to get this position wrong, both of which look like the fix
    is broken: standing at (12, 0) puts the barrel BETWEEN him and an
    enemy at the origin, so he is already covered (the next test's case);
    and standing further out than a Half Move from the covered spot is
    refused on distance, which is a different gate entirely."""
    assert _cover_offers(_menu((8.0, 5.0)))


def test_a_man_already_behind_the_barrel_is_not_offered_it_again():
    """Standing 1m past it on the far side from the enemy --- exactly
    where the offer would have sent him."""
    assert not _cover_offers(_menu((6.0, 0.0)))


def test_he_can_still_shoot():
    """Guards the point of the fix: removing the no-op offer must leave
    the attack there, or the man behind the barrel has nothing to do."""
    menu = _menu((6.0, 0.0))
    assert [a for a in menu if a.kind == "attack"]
