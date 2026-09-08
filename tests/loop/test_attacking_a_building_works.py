"""Shooting a wall actually damages it.

`attack_construct` has been in `ALL_ACTION_KINDS` and had a registered
resolver for a long time, and it has never once resolved. Two bugs, both
invisible because nothing could reach the code: no scene ever put a wall
into `constructs`, so the resolver was never called.

    1. it looked the target up with `getattr(c, "id", None)`, and
       `Construct`'s field is `obj_id` --- so the lookup always failed and
       the action raised `UnresolvableAction` every time;
    2. it called `apply_attack_to_construct(construct, body_dealt=...)`
       against a signature of `(power, dice, construct, template)`.

Both surfaced the same afternoon the walls were finally projected in ---
`skipped: {'attack_construct': 2}` --- which is the argument for making
dead code reachable rather than leaving it to rot: it looked finished.

6E2 p.172: objects take BODY and break, and have no STUN behaviour at
all.
"""
from __future__ import annotations

from conftest import blast, fighter               # tests/loop/conftest.py
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.scene.construct import constructs_in
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _session(body=8, def_value=2):
    wall = Wall(id="shack", name="Fly's Studio",
                segment=(Position(3.0, 1.0, 0.0), Position(3.0, 5.0, 0.0)),
                height_m=4.0, blocks_los=True, blocks_movement=True,
                cover_level=4, body=body, def_value=def_value)
    scene = Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 12.0, 12.0, 12.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (12, -2), (12, 12), (-2, 12)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[wall], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"a": Position(1.0, 3.0, 0.0),
                             "b": Position(8.0, 8.0, 0.0)},
        constructs=constructs_in_of(wall),
    )
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE,
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter("a", side=Side.named("x")),
                    fighter("b", side=Side.named("y"))],
    ).start()


def constructs_in_of(wall):
    from kirby_combat.scene.construct import construct_from_wall

    return [construct_from_wall(wall)]


def _offer(session):
    actor = session.combatants["a"]
    menu = enumerate_actions(
        actor, [session.combatants["b"]], has_scene=True, scene=session.scene,
        constructs=constructs_in(session.scene) or None,
        movement=list(actor.movement_view()),
    )
    return next(a for a in menu if a.kind == "attack_construct")


def test_the_shot_resolves_at_all():
    """It raised `UnresolvableAction` every time, because the lookup asked
    for `id` and a Construct has `obj_id`."""
    session = _session()
    resolved = resolve_chosen(session, session.combatants["a"], _offer(session),
                              template=TEMPLATE, roller=RandomRoller(seed=5))
    assert resolved is not None


def test_the_building_loses_body():
    session = _session(body=8, def_value=0)
    before = next(c for c in session.scene.constructs if c.obj_id == "shack").body
    resolved = resolve_chosen(session, session.combatants["a"], _offer(session),
                              template=TEMPLATE, roller=RandomRoller(seed=5))
    payload = [e for e in resolved.events
               if getattr(e, "kind", "") == "ActionResolved"][-1].result_payload
    assert payload.get("body_dealt", 0) > 0, payload
    assert before == 8
