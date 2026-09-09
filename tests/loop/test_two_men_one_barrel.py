"""Two men do not stand in the same place.

Read off the O.K. Corral's final positions:

    billy_clanton  (1.30, 3.20)
    tom_mclaury    (1.30, 3.20)
    morgan_earp    (3.30, 3.20)
    wyatt_earp     (3.30, 3.20)

At Turn 2 Segment 4 five men all chose `move_to_cover:barrels`, and
`move_to_cover` computes ONE covered spot per wall and sends everybody to
it. Nothing asked whether somebody was already standing there, so they
ended the fight in pairs, inside each other.

A JUDGEMENT, and marked as one. 6E has no rule about two characters
occupying the same space --- it assumes a hex map, where a hex holding one
character is a convention rather than a printed rule, so there is nothing
to cite. What there is: a fighter does not walk into another fighter and
stop there.

Fixed in the MENU, like every other offer that could not deliver what it
promised: the cover behind a barrel two men are already using is not
cover this man can take.
"""
from __future__ import annotations

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.side import Side


def _lot(**positions):
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 12.0, 12.0, 12.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (12, -2), (12, 12), (-2, 12)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[Wall(id="barrels", name="Stack of whiskey barrels",
                    segment=(Position(4.0, 4.0, 0.0), Position(4.0, 5.0, 0.0)),
                    height_m=1.2, blocks_los=False, blocks_movement=True,
                    cover_level=2, body=4, def_value=2, climb_difficulty=0)],
        hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={k: Position(*v, 0.0) for k, v in positions.items()},
    )


def _cover_offers(scene, actor_id="wyatt"):
    actor = fighter(actor_id, side=Side.named("law"))
    enemy = fighter("frank", side=Side.named("cow"))
    menu = enumerate_actions(
        actor, [enemy], has_scene=True, scene=scene,
        movement=list(actor.movement_view()),
    )
    return [a for a in menu if a.kind == "move_to_cover"]


def test_a_free_barrel_is_offered():
    """Guards the guard --- the ordinary case must keep working.

    Wyatt stands north of the barrels with nothing between him and Frank,
    so the covered spot is a move away rather than one he is already in.
    (Standing beside them yields no offer at all, correctly: today's
    earlier fix stops the menu offering cover a man already has.)
    """
    scene = _lot(wyatt=(2.0, 9.0), frank=(9.0, 4.5))
    assert _cover_offers(scene)


def test_a_barrel_somebody_is_already_behind_is_not():
    """The defect. Morgan is in the only covered spot; Wyatt cannot stand
    inside him."""
    spot = _the_spot(_lot(wyatt=(2.0, 9.0), frank=(9.0, 4.5)))
    scene = _lot(wyatt=(2.0, 9.0), morgan=spot, frank=(9.0, 4.5))
    assert not _cover_offers(scene), (
        "offered a spot another man is standing in"
    )


def test_a_man_far_from_the_spot_does_not_block_it():
    scene = _lot(wyatt=(2.0, 9.0), morgan=(11.0, 11.0), frank=(9.0, 4.5))
    assert _cover_offers(scene)


def _the_spot(scene) -> tuple[float, float]:
    """Where the menu would send him, so a test can put somebody there."""
    offer = _cover_offers(scene)[0]
    x, y, _z = offer.reposition_dest
    return (x, y)

