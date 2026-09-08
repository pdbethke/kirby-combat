"""Leaving a fight --- the thing the engine could never do.

Sixty action kinds and not one of them was flee, withdraw, retreat or
disengage. Every combatant fought until unconscious or dying, because
those were the only two ways the loop knew a fighter could stop.

That is not a small gap. Every `move` offer the engine makes is
`move:<enemy>` --- TOWARD somebody. `reposition` breaks contact, but only
for a specific fragile-versus-heavy matchup already inside melee reach,
so in a gunfight it never fires. There was literally no way to walk away.

It shows plainest at the O.K. Corral. Ike Clanton and Billy Claiborne
were UNARMED --- Wyatt told Ike so and let him go, and both ran into
Fly's. In the simulation they stayed, and punched four armed men for 0
STUN a phase until they were shot. A man with no gun in a gunfight runs,
and the engine had no word for it.

The book does not need a Flee maneuver: moving away is just moving. What
was missing is an OFFER that goes the other way, and a definition of
having left --- which is a stop-condition question, and `Roster` already
owns those.

RAW hook for the consequence, not the movement: 6E2 p.139 puts "may
surrender, run away or faint" at PRE+30. The engine consumes that tier's
0 DCV and its cannot-act, and had no way to express the running.
"""
from __future__ import annotations

import math
from dataclasses import replace

import pytest

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.enumeration import ALL_ACTION_KINDS, enumerate_actions
from kirby_combat.encounter import Encounter
from kirby_combat.loop import Roster, next_actor_id
from kirby_combat.loop.registry import registered_kinds, resolve_chosen
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _scene(runner_at=(10.0, 0.0), chaser_at=(0.0, 0.0)):
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -20.0, 0.0, 30.0, 20.0, 10.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -20), (30, -20), (30, 20), (-2, 20)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={
            "runner": Position(runner_at[0], runner_at[1], 0.0),
            "chaser": Position(chaser_at[0], chaser_at[1], 0.0),
        },
    )


def _session(scene=None):
    return CombatSession.create(
        id="s", scene=scene if scene is not None else _scene(),
        template=TEMPLATE, dice_roller=RandomRoller(seed=5),
        combatants=[fighter("runner", side=Side.named("a"), dex=20),
                    fighter("chaser", side=Side.named("b"), dex=15)],
    ).start()


def _menu(session):
    actor = session.combatants["runner"]
    enemies = [session.combatants["chaser"]]
    return enumerate_actions(actor, enemies, scene=session.scene,
                             has_scene=True,
                             movement=list(actor.movement_view()))


# ---- The kind exists ----

def test_disengage_is_a_declared_kind():
    assert "disengage" in ALL_ACTION_KINDS


def test_disengage_has_a_resolver():
    assert "disengage" in registered_kinds()


# ---- It is offered, and it goes the RIGHT WAY ----

def test_a_fighter_on_a_map_is_offered_a_way_out():
    assert [a for a in _menu(_session()) if a.kind == "disengage"]


def test_the_offer_moves_away_from_the_enemy_not_toward_them():
    """The whole point. Every other move offer closes the distance."""
    session = _session()
    offer = next(a for a in _menu(session) if a.kind == "disengage")
    dest_x = offer.reposition_dest[0]
    assert dest_x > 10.0, (
        f"runner is at x=10 with the enemy at x=0; a disengage must "
        f"increase the distance, but the destination is x={dest_x}"
    )


def test_no_scene_means_no_offer():
    """Nowhere to run to, and no way to say how far you got."""
    session = CombatSession.create(
        id="s", scene=None, template=TEMPLATE,
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter("runner", side=Side.named("a")),
                    fighter("chaser", side=Side.named("b"))],
    ).start()
    actor = session.combatants["runner"]
    menu = enumerate_actions(actor, [session.combatants["chaser"]])
    assert not [a for a in menu if a.kind == "disengage"]


# ---- Resolving it actually moves you ----

def test_disengaging_opens_the_range():
    session = _session()
    offer = next(a for a in _menu(session) if a.kind == "disengage")
    resolved = resolve_chosen(session, session.combatants["runner"], offer,
                              template=TEMPLATE, roller=RandomRoller(seed=5))
    after = resolved.session.scene.combatant_positions["runner"]
    assert after.x > 10.0


# ---- Having left means being out ----

def test_a_fighter_who_leaves_the_field_is_no_longer_standing():
    """`Roster.standing` knew two ways to stop fighting, unconscious and
    dying. Walking away is the third, and a fight where one side has run
    is over --- otherwise the loop hunts a man who is already gone."""
    scene = _scene(runner_at=(29.5, 0.0))          # at the boundary
    session = _session(scene)
    offer = next(a for a in _menu(session) if a.kind == "disengage")
    resolved = resolve_chosen(session, session.combatants["runner"], offer,
                              template=TEMPLATE, roller=RandomRoller(seed=5))
    standing = Roster(resolved.session).standing
    assert Side.named("a") not in standing, (
        "the runner left the field and should not count as standing"
    )
    assert Side.named("b") in standing


def test_someone_still_on_the_field_is_still_standing():
    """Guards the guard: an ordinary disengage that stays in bounds must
    NOT remove the fighter from the fight."""
    session = _session()
    offer = next(a for a in _menu(session) if a.kind == "disengage")
    resolved = resolve_chosen(session, session.combatants["runner"], offer,
                              template=TEMPLATE, roller=RandomRoller(seed=5))
    assert Side.named("a") in Roster(resolved.session).standing


# ---- A wall behind you ----
#
# The O.K. Corral found this one, and only the Phase-by-Phase account
# could: Ike Clanton --- unarmed, the exact man `withdraw_when_outmatched`
# exists for --- chose `disengage` three Phases running, moved ZERO metres
# on the last two, and was shot standing still at (0.0, 2.1) with his back
# against the Harwood House wall.
#
# The offer said "run 12m directly away from them, opening the range by
# about 12m". It was computed as pure geometry --- the unit vector away
# from the enemies' centroid, times the movement budget --- and never
# asked whether the actor could GO there. Ike's away-vector pointed into a
# `blocks_movement` wall, `movement_reach` clamped him to nothing, and the
# menu offered the same impossible escape again the next Phase.
#
# Same shape as the cover trap fixed in c090c37b: an offer that cannot
# deliver what it promises, repeated for ever. And the same fix --- in the
# MENU, not the chooser. A man with his back to a wall runs ALONG it.
#
# Every test above this line builds its scene with `walls=[]`, which is
# why none of them could have caught it.

def _walled_scene(walls, runner_at=(10.0, 0.0), chaser_at=(0.0, 0.0)):
    scene = _scene(runner_at=runner_at, chaser_at=chaser_at)
    return replace(scene, walls=walls)


def _wall(id_, a, b):
    return Wall(id=id_, name=id_,
                segment=(Position(a[0], a[1], 0.0), Position(b[0], b[1], 0.0)),
                height_m=4.0, blocks_los=True, blocks_movement=True,
                cover_level=4, body=8, def_value=4, climb_difficulty=-3)


def _distance_from_chaser(session, who="runner"):
    pos = session.scene.combatant_positions[who]
    foe = session.scene.combatant_positions["chaser"]
    return math.dist((pos.x, pos.y), (foe.x, foe.y))


def test_a_wall_behind_you_does_not_make_the_offer_a_lie():
    """The offered escape must be one the actor can actually take.

    The runner is at (10, 0) with the chaser at the origin, so straight
    away is +x --- and a blocking wall stands at x=11. Running along it
    still opens the range; running into it does not. The offer has to be
    the one that works.
    """
    session = _session(_walled_scene([_wall("behind", (11.0, -20.0), (11.0, 20.0))]))
    before = _distance_from_chaser(session)
    offer = next(a for a in _menu(session) if a.kind == "disengage")
    resolved = resolve_chosen(session, session.combatants["runner"], offer,
                              template=TEMPLATE, roller=RandomRoller(seed=5))
    assert _distance_from_chaser(resolved.session) > before + 1.0, (
        "disengage was offered but the actor could not go there: the "
        "destination was picked as geometry and never checked for reach"
    )


def test_a_boxed_in_fighter_is_offered_no_way_out():
    """Guards the guard. Where NO heading opens the range, there is no
    disengage --- an offer that cannot move you is worse than no offer,
    because a chooser reading the doctrine will take it every Phase.

    The box is deliberately smaller than the threshold: a roomier one is
    not a trap at all --- a man who can cross two metres to a far corner
    HAS opened the range, and the offer telling him so is true."""
    session = _session(_walled_scene([
        _wall("n", (9.6, 0.4), (10.4, 0.4)),
        _wall("s", (9.6, -0.4), (10.4, -0.4)),
        _wall("e", (10.4, -0.4), (10.4, 0.4)),
        _wall("w", (9.6, -0.4), (9.6, 0.4)),
    ]))
    assert not [a for a in _menu(session) if a.kind == "disengage"]


def test_a_fighter_who_has_left_is_skipped_not_asked():
    """Leaving has to reach the LOOP, not just the scoreboard.

    `Roster.standing` reads the bounds and correctly stops counting a man
    who has gone. `next_actor_id` never asked. At the O.K. Corral, Billy
    Claiborne was off the field at y=-11 by Turn 2 Segment 4 and was
    still handed a Phase at Segment 8, in which he ran to y=-23 --- the
    loop hunting a man who was already through the door.

    Same shape as the downed case one line above it in `next_actor_id`,
    and the same treatment: consume the slot, never enumerate for him.
    """
    session = _session(_scene(runner_at=(60.0, 0.0)))    # bounds end at x=30
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    roller = RandomRoller(seed=3)
    enc = enc.run_segment(roller=lambda: roller.roll_dice(3))

    # The runner has the higher DEX, so he would be first if asked at all.
    assert next_actor_id(enc.sessions[0]) == "chaser"
