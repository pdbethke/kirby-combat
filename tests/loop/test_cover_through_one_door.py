"""Cover through one door: the offer to take cover and the Brief's sightings.

kirby-combat read cover in two private loops --- `enumerate_actions` for the
`move_to_cover` offers and `Terrain.sightings` for the Brief --- each walking
`scene.walls` on its own. Both now ask `kirby_world.cover.cover_spots`, so
what is offered, what the page says and what the threat picture ranks cannot
drift apart.

THESE ARE SEAM TESTS, WRITTEN FIRST. The snapshots below were taken from the
code BEFORE the rewrite, on the O.K. Corral's own lot, and must still hold
after it: a refactor that changes what a fighter is offered has changed the
game, not tidied it.
"""
from __future__ import annotations

from conftest import fighter  # tests/loop/conftest.py
from kirby_combat.brief import Terrain
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.loop import Roster
from kirby_combat.loop.run import distances_from
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller
from kirby_world.scene import (
    AmbientConditions, Furnishing, Position, Scene, SceneBounds, Surface,
)

TEMPLATE = CombatTemplate.default_6e_superheroic()
LAW = ("morgan_earp", "wyatt_earp", "virgil_earp", "doc_holliday")


def _corral_session():
    from examples.the_ok_corral import the_lot

    scene = the_lot()
    law, cow = Side.named("Earps"), Side.named("Cowboys")
    return CombatSession.create(
        id="corral", scene=scene, template=TEMPLATE,
        dice_roller=RandomRoller(seed=4),
        combatants=[
            fighter(cid, side=law if cid in LAW else cow, dex=20)
            for cid in scene.combatant_positions
        ],
    ).start()


def _offers(session, actor_id):
    actor = session.combatants[actor_id]
    enemies = Roster(session).enemies_of(actor)
    menu = enumerate_actions(
        actor, enemies, has_scene=True, scene=session.scene,
        distances=distances_from(session.scene, actor, enemies),
    )
    return sorted(
        (a.action_id, tuple(round(c, 2) for c in a.reposition_dest), a.summary)
        for a in menu if a.kind == "move_to_cover"
    )


def _sightings(session, actor_id):
    actor = session.combatants[actor_id]
    return Terrain(session, actor, Roster(session).enemies_of(actor)).sightings


# ---- The O.K. Corral ----

# {actor: [(action_id, (x, y, z), summary)]} as the pre-rewrite code offered it.
CORRAL_OFFERS = {'morgan_earp': [('move_to_cover:crates',
                  (3.6, 7.6, 0.0),
                  'Take cover behind Packing crates (0.6m away) — cover 3/4 against 2 '
                  'of 5 of them, so those attackers take -4 OCV against you; 3 of 5 '
                  'would still have a clear shot. Half Move, so you may still attack '
                  '(6E2 p45)')],
 'virgil_earp': [('move_to_cover:barrels',
                  (3.3, 3.2, 0.0),
                  'Take cover behind Stack of whiskey barrels (0.8m away) — cover 2/4 '
                  'against 1 of 5 of them, so those attackers take -2 OCV against you; '
                  '4 of 5 would still have a clear shot. Half Move, so you may still '
                  'attack (6E2 p45)'),
                 ('move_to_cover:flys-studio',
                  (6.5, 1.0, 0.0),
                  "Take cover behind C.S. Fly's Studio (south-east) (4.2m away) — "
                  'cover 4/4 against 4 of 5 of them, so those attackers take -8 OCV '
                  'against you; 1 of 5 would still have a clear shot. Half Move, so '
                  'you may still attack (6E2 p45)')]}

# {actor: [sighting line]} as the pre-rewrite Brief wrote it.
CORRAL_SIGHTINGS = {'billy_claiborne': ['Harwood House (west wall): 5.3m away, would give you cover 4/4; '
                     'DEF 4, BODY 3 to break through',
                     "C.S. Fly's Lodgings (east wall): 5.6m away, would give you cover "
                     '4/4; DEF 4, BODY 3 to break through',
                     "C.S. Fly's Studio (south-east): 2.0m away, would not shield you "
                     'from where they are; DEF 4, BODY 3 to break through',
                     "Photographer's wagon: 8.5m away, would give you cover 2/4; DEF "
                     '3, BODY 12 to break through',
                     'Stack of whiskey barrels: 2.5m away, would give you cover 2/4; '
                     'DEF 2, BODY 4 to break through',
                     'Water trough: 4.6m away, would not shield you from where they '
                     'are; DEF 3, BODY 5 to break through',
                     'Packing crates: 6.7m away, would give you cover 3/4; DEF 2, BODY '
                     '4 to break through'],
 'billy_clanton': ['Harwood House (west wall): 2.9m away, would give you cover 4/4; '
                   'DEF 4, BODY 3 to break through',
                   "C.S. Fly's Lodgings (east wall): 5.5m away, would give you cover "
                   '4/4; DEF 4, BODY 3 to break through',
                   "C.S. Fly's Studio (south-east): 4.3m away, would not shield you "
                   'from where they are; DEF 4, BODY 3 to break through',
                   "Photographer's wagon: 7.1m away, would give you cover 2/4; DEF 3, "
                   'BODY 12 to break through',
                   'Stack of whiskey barrels: 1.1m away, would give you cover 2/4; DEF '
                   '2, BODY 4 to break through',
                   'Water trough: 3.4m away, would not shield you from where they are; '
                   'DEF 3, BODY 5 to break through',
                   'Packing crates: 5.2m away, would give you cover 3/4; DEF 2, BODY 4 '
                   'to break through'],
 'doc_holliday': ['Harwood House (west wall): 4.3m away, would give you cover 4/4; DEF '
                  '4, BODY 3 to break through',
                  "C.S. Fly's Lodgings (east wall): 3.8m away, would give you cover "
                  '4/4; DEF 4, BODY 3 to break through',
                  "C.S. Fly's Studio (south-east): 8.1m away, would give you cover "
                  '4/4; DEF 4, BODY 3 to break through',
                  "Photographer's wagon: 1.0m away, would give you cover 2/4; DEF 3, "
                  'BODY 12 to break through',
                  'Stack of whiskey barrels: 5.3m away, would give you cover 2/4; DEF '
                  '2, BODY 4 to break through',
                  'Water trough: 2.9m away, would give you cover 2/4; DEF 3, BODY 5 to '
                  'break through',
                  'Packing crates: 0.9m away, would give you cover 3/4; DEF 2, BODY 4 '
                  'to break through'],
 'frank_mclaury': ['Harwood House (west wall): 1.6m away, would give you cover 4/4; '
                   'DEF 4, BODY 3 to break through',
                   "C.S. Fly's Lodgings (east wall): 4.1m away, would give you cover "
                   '4/4; DEF 4, BODY 3 to break through',
                   "C.S. Fly's Studio (south-east): 6.0m away, would not shield you "
                   'from where they are; DEF 4, BODY 3 to break through',
                   "Photographer's wagon: 4.2m away, would give you cover 2/4; DEF 3, "
                   'BODY 12 to break through',
                   'Stack of whiskey barrels: 2.4m away, would give you cover 2/4; DEF '
                   '2, BODY 4 to break through',
                   'Water trough: 1.5m away, would not shield you from where they are; '
                   'DEF 3, BODY 5 to break through',
                   'Packing crates: 2.4m away, would give you cover 3/4; DEF 2, BODY 4 '
                   'to break through'],
 'ike_clanton': ['Harwood House (west wall): 1.8m away, would give you cover 4/4; DEF '
                 '4, BODY 3 to break through',
                 "C.S. Fly's Lodgings (east wall): 4.6m away, would give you cover "
                 '4/4; DEF 4, BODY 3 to break through',
                 "C.S. Fly's Studio (south-east): 5.0m away, would not shield you from "
                 'where they are; DEF 4, BODY 3 to break through',
                 "Photographer's wagon: 5.6m away, would give you cover 2/4; DEF 3, "
                 'BODY 12 to break through',
                 'Stack of whiskey barrels: 1.1m away, would give you cover 2/4; DEF '
                 '2, BODY 4 to break through',
                 'Water trough: 2.2m away, would not shield you from where they are; '
                 'DEF 3, BODY 5 to break through',
                 'Packing crates: 3.8m away, would give you cover 3/4; DEF 2, BODY 4 '
                 'to break through'],
 'morgan_earp': ['Harwood House (west wall): 4.0m away, would give you cover 4/4; DEF '
                 '4, BODY 3 to break through',
                 "C.S. Fly's Lodgings (east wall): 2.1m away, would give you cover "
                 '4/4; DEF 4, BODY 3 to break through',
                 "C.S. Fly's Studio (south-east): 6.3m away, would give you cover 4/4; "
                 'DEF 4, BODY 3 to break through',
                 "Photographer's wagon: 2.6m away, would give you cover 2/4; DEF 3, "
                 'BODY 12 to break through',
                 'Stack of whiskey barrels: 4.0m away, would give you cover 2/4; DEF '
                 '2, BODY 4 to break through',
                 'Water trough: 1.5m away, would give you cover 2/4; DEF 3, BODY 5 to '
                 'break through',
                 'Packing crates: 1.1m away, would give you cover 3/4; DEF 2, BODY 4 '
                 'to break through'],
 'tom_mclaury': ['Harwood House (west wall): 2.5m away, would give you cover 4/4; DEF '
                 '4, BODY 3 to break through',
                 "C.S. Fly's Lodgings (east wall): 4.1m away, would give you cover "
                 '4/4; DEF 4, BODY 3 to break through',
                 "C.S. Fly's Studio (south-east): 7.2m away, would not shield you from "
                 'where they are; DEF 4, BODY 3 to break through',
                 "Photographer's wagon: 2.8m away, would give you cover 2/4; DEF 3, "
                 'BODY 12 to break through',
                 'Stack of whiskey barrels: 3.9m away, would give you cover 2/4; DEF '
                 '2, BODY 4 to break through',
                 'Water trough: 2.1m away, would not shield you from where they are; '
                 'DEF 3, BODY 5 to break through',
                 'Packing crates: 1.3m away, would not shield you from where they are; '
                 'DEF 2, BODY 4 to break through'],
 'virgil_earp': ['Harwood House (west wall): 3.6m away, would give you cover 4/4; DEF '
                 '4, BODY 3 to break through',
                 "C.S. Fly's Lodgings (east wall): 3.0m away, would give you cover "
                 '4/4; DEF 4, BODY 3 to break through',
                 "C.S. Fly's Studio (south-east): 3.6m away, would give you cover 4/4; "
                 'DEF 4, BODY 3 to break through',
                 "Photographer's wagon: 5.6m away, would give you cover 2/4; DEF 3, "
                 'BODY 12 to break through',
                 'Stack of whiskey barrels: 1.4m away, would give you cover 2/4; DEF '
                 '2, BODY 4 to break through',
                 'Water trough: 1.7m away, would give you cover 2/4; DEF 3, BODY 5 to '
                 'break through',
                 'Packing crates: 3.7m away, would give you cover 3/4; DEF 2, BODY 4 '
                 'to break through'],
 'wyatt_earp': ['Harwood House (west wall): 3.5m away, would give you cover 4/4; DEF '
                '4, BODY 3 to break through',
                "C.S. Fly's Lodgings (east wall): 2.1m away, would give you cover 4/4; "
                'DEF 4, BODY 3 to break through',
                "C.S. Fly's Studio (south-east): 4.9m away, would give you cover 4/4; "
                'DEF 4, BODY 3 to break through',
                "Photographer's wagon: 4.1m away, would give you cover 2/4; DEF 3, "
                'BODY 12 to break through',
                'Stack of whiskey barrels: 2.6m away, would give you cover 2/4; DEF 2, '
                'BODY 4 to break through',
                'Water trough: 0.5m away, would give you cover 2/4; DEF 3, BODY 5 to '
                'break through',
                'Packing crates: 2.3m away, would give you cover 3/4; DEF 2, BODY 4 to '
                'break through']}



def test_the_corral_offers_the_same_cover():
    session = _corral_session()
    got = {cid: _offers(session, cid) for cid in session.scene.combatant_positions}
    assert {k: v for k, v in got.items() if v} == CORRAL_OFFERS


def test_the_corral_brief_says_the_same_things():
    session = _corral_session()
    got = {cid: _sightings(session, cid) for cid in session.scene.combatant_positions}
    assert got == CORRAL_SIGHTINGS


# ---- A scene with a furnishing ----

def _yard(*, shooter_at=(10.0, 5.0), actor_at=(4.0, 5.0)):
    scene = Scene(
        id="yard", name="A yard", bounds=SceneBounds(-30, -30, 0, 30, 30, 10),
        surfaces=[Surface(id="ground", name="Ground",
                          polygon_xy=[(-30, -30), (30, -30), (30, 30), (-30, 30)],
                          elevation_m=0.0, surface_type="ground", cover_level=0,
                          is_supporting=True)],
        walls=[], hazards=[], ambient=AmbientConditions(),
        furnishings=[Furnishing(
            id="wagon", name="Hay wagon",
            polygon_xy=[(3.0, -2.0), (5.0, -2.0), (5.0, 2.0), (3.0, 2.0)],
            height_m=1.5, material="wooden wall", body=6, cover_level=3,
        )],
        combatant_positions={
            "actor": Position(*actor_at, 0.0), "mark": Position(*shooter_at, 0.0),
        },
    )
    return CombatSession.create(
        id="yard", scene=scene, template=TEMPLATE,
        dice_roller=RandomRoller(seed=4),
        combatants=[fighter("actor", side=Side.named("a"), dex=20),
                    fighter("mark", side=Side.named("b"), dex=15)],
    ).start()


# INTENDED CHANGE (task 7): a furnishing is ONE feature, so the offer is
# `move_to_cover:wagon`, not `move_to_cover:wagon#edge3`. The spot, the
# summary and the cover it quotes are exactly what the per-edge loop offered.
YARD_OFFERS = [('move_to_cover:wagon',
  (2.0, 0.0, 0.0),
  'Take cover behind Hay wagon (5.4m away) — cover 3/4 against 1 of 1 of them, so '
  'those attackers take -4 OCV against you. Half Move, so you may still attack (6E2 '
  'p45)')]
YARD_SIGHTINGS = ['Hay wagon: 3.0m away, would give you cover 3/4; DEF 4, BODY 6 to break '
 'through']


def test_a_furnishing_is_one_offer():
    assert _offers(_yard(), "actor") == YARD_OFFERS


def test_a_furnishing_is_one_line_on_the_page():
    assert _sightings(_yard(), "actor") == YARD_SIGHTINGS
