"""Cover you cannot shoot from is a hiding place, not a firing position.

Virgil Earp took cover behind Fly's Studio at (6.5, 1.0) and could target
NOBODY --- the building blocks line of sight, so `perceive(...)
.targetable_physical` was False for all three Cowboys. `attack` vanished
from his menu, the four tactics that want it fell through, and the only
fight-shaped offer left was shooting the building he was hiding behind.

He spent half the fight doing exactly that. Measured over 25 seeded runs:
Virgil falls through to the fallback on 51% of his decisions, more than
any other man in the lot, and every one of those Phases he shoots a wall.

PeterB: "virgil's goal should be kill the cowboys, not shoot buildings".

THE OFFER IS THE PLACE TO FIX IT, as it has been all day. Cover is not an
end in itself --- it is somewhere to shoot FROM. A spot that blocks
everyone he came to fight is a spot that serves survival and nothing
else, and the menu should not offer it as though it were tactics.

Cover that blocks SOME of them is still cover, and is still offered: the
whole point of `cover_breakdown` is that hiding from one man while four
others walk around it is a real trade a fighter can choose.
"""
from __future__ import annotations

from conftest import blast, fighter               # tests/loop/conftest.py
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.side import Side


def _lot(*walls, **positions):
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 14.0, 14.0, 14.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (14, -2), (14, 14), (-2, 14)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=list(walls), hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={k: Position(*v, 0.0) for k, v in positions.items()},
    )


def _wall(id_, x, y0, y1, *, blocks_los):
    return Wall(id=id_, name=id_,
                segment=(Position(x, y0, 0.0), Position(x, y1, 0.0)),
                height_m=2.0, blocks_los=blocks_los, blocks_movement=True,
                cover_level=4 if blocks_los else 2,
                body=6, def_value=2, climb_difficulty=0)


def _cover_offers(scene, actor_id="virgil"):
    actor = fighter(actor_id, side=Side.named("law"))
    enemy = fighter("billy", side=Side.named("cow"))
    menu = enumerate_actions(
        actor, [enemy], has_scene=True, scene=scene,
        movement=list(actor.movement_view()),
    )
    return [a for a in menu if a.kind == "move_to_cover"]


def test_cover_that_blinds_him_completely_is_not_offered():
    """Fly's Studio. Safe, and he cannot shoot a soul from behind it.

    GEOMETRY VERIFIED FIRST: this exact scene DOES offer
    `move_to_cover:studio` at (4.0, 4.5) today, and from there the wall
    sits between him and Billy. A longer wall produces no offer at all for
    unrelated reasons, so a test written against one would have passed
    without proving anything --- which is how the first draft of this file
    was written.
    """
    scene = _lot(_wall("studio", 5.0, 4.0, 5.0, blocks_los=True),
                 virgil=(2.0, 9.0), billy=(9.0, 4.5))
    assert not _cover_offers(scene), (
        "offered a firing position he cannot fire from"
    )


def test_cover_he_can_still_shoot_over_is_offered():
    """A low wall --- the barrels. Free DCV and he keeps his shot, which is
    the trade cover is supposed to be."""
    scene = _lot(_wall("barrels", 5.0, 4.0, 5.0, blocks_los=False),
                 virgil=(2.0, 9.0), billy=(9.0, 4.5))
    assert _cover_offers(scene)


def test_cover_that_blocks_only_one_of_them_is_still_offered():
    """`cover_breakdown` exists because hiding from one man while others
    walk around it is a real choice. This must not take that away.

    Frank stands where the wall does NOT come between them, so from the
    covered spot Virgil is blind to Billy and can still shoot Frank ---
    which is cover doing its job rather than hiding him from the fight.
    """
    # GEOMETRY VERIFIED: this placement genuinely offers
    # `move_to_cover:studio` at (4.0, 4.5), and from there the wall blocks
    # Billy and not Frank. Putting Frank on the far side instead offers no
    # cover at all --- correctly, since no spot covers against both --- and a
    # test written that way would have proved nothing.
    scene = _lot(_wall("studio", 5.0, 4.0, 5.0, blocks_los=True),
                 virgil=(2.0, 9.0), billy=(9.0, 4.5), frank=(9.0, 9.0))
    actor = fighter("virgil", side=Side.named("law"))
    menu = enumerate_actions(
        actor,
        [fighter("billy", side=Side.named("cow")),
         fighter("frank", side=Side.named("cow"))],
        has_scene=True, scene=scene, movement=list(actor.movement_view()),
    )
    assert [a for a in menu if a.kind == "move_to_cover"]
