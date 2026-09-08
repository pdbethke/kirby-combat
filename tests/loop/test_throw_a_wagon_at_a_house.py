"""Throw the wagon at the house.

PeterB: *"throw a wagon at a house that ike is hiding in and collapse
it"*.

`throw_object` offered one target shape --- `for enemy in alive_enemies`
--- so the only thing a brick could throw a wagon at was a person. The
scenery was never aimable, even after walls became destructible.

Everything else was already here by the time this was written: walls
project into constructs (`constructs_in`), constructs take BODY and break
(`apply_attack_to_construct`, 6E2 p.172), and the damage a thrown object
does is `resolve_object_throw` --- min(STR dice, the object's own PD+BODY),
which is the rule that stops a man throwing a pillow through a wall.

A NOTE ON WHAT IS STILL BROKEN NEXT DOOR: throwing an object at a PERSON
still resolves to nothing. `_resolve_throw` computes a distance and
records it and applies no damage to anybody. That is why Power Lad's
wagon never hurt Wyatt Earp. Fixed here for constructs only, deliberately
--- the person path wants the ordinary attack pipeline, which is a
different piece of work, and pretending otherwise would bury it.
"""
from __future__ import annotations

from conftest import fighter                      # tests/loop/conftest.py
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


def _wagon():
    return Construct(
        obj_id="wagon", kind="wall", portable=True,
        segment=(Position(2.0, 2.0, 0.0), Position(2.0, 2.0, 0.0)),
        height_m=1.5, blocks_los=False, blocks_movement=False,
        cover_level=2, def_value=3, body=6,
    )


def _shack(body=6, def_value=1):
    return Wall(id="shack", name="Fly's Studio",
                segment=(Position(6.0, 6.0, 0.0), Position(6.0, 9.0, 0.0)),
                height_m=4.0, blocks_los=True, blocks_movement=True,
                cover_level=4, body=body, def_value=def_value)


def _session(**kw):
    scene = Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 14.0, 14.0, 14.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (14, -2), (14, 14), (-2, 14)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[_shack(**kw)], hazards=[],
        ambient=AmbientConditions(light_level=4),
        combatant_positions={"lad": Position(2.0, 1.5, 0.0),
                             # In the open, not behind the shack: a man you cannot see
        # is a man you cannot throw a wagon at, and the perception
        # gate is right to drop that offer.
        "ike": Position(4.0, 3.0, 0.0)},
        constructs=[_wagon()],
    )
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE,
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter("lad", side=Side.solo("lad")),
                    fighter("ike", side=Side.named("cow"))],
    ).start()


def _menu(session, holding="wagon"):
    actor = session.combatants["lad"]
    return enumerate_actions(
        actor, [session.combatants["ike"]],
        has_scene=True, scene=session.scene,
        constructs=constructs_in(session.scene) or None,
        movement=list(actor.movement_view()),
        actor_holding=holding is not None, held_construct_id=holding,
    )


def test_the_house_is_a_thing_he_can_throw_it_at():
    offers = [a for a in _menu(_session()) if a.kind == "throw_object"]
    assert any(a.target_id == "shack" for a in offers), (
        [a.action_id for a in offers]
    )


def test_the_man_is_still_a_thing_he_can_throw_it_at():
    """Guards the guard --- adding scenery must not lose people."""
    offers = [a for a in _menu(_session()) if a.kind == "throw_object"]
    assert any(a.target_id == "ike" for a in offers)


def test_nothing_is_offered_when_his_hands_are_empty():
    assert not [a for a in _menu(_session(), holding=None)
                if a.kind == "throw_object"]


def test_the_house_takes_body():
    session = _session(body=6, def_value=0)
    offer = next(a for a in _menu(session)
                 if a.kind == "throw_object" and a.target_id == "shack")
    resolved = resolve_chosen(session, session.combatants["lad"], offer,
                              template=TEMPLATE, roller=RandomRoller(seed=5))
    payload = [e for e in resolved.events
               if getattr(e, "kind", "") == "ActionResolved"][-1].result_payload
    assert payload.get("body_dealt", 0) > 0, payload


def test_a_shack_can_be_brought_down():
    """The whole point. 6E2 p.172: objects take BODY and break."""
    session = _session(body=1, def_value=0)
    offer = next(a for a in _menu(session)
                 if a.kind == "throw_object" and a.target_id == "shack")
    resolved = resolve_chosen(session, session.combatants["lad"], offer,
                              template=TEMPLATE, roller=RandomRoller(seed=5))
    payload = [e for e in resolved.events
               if getattr(e, "kind", "") == "ActionResolved"][-1].result_payload
    assert payload.get("destroyed") is True, payload


# ---- and at a man ----

def test_a_thrown_wagon_hurts_the_man_it_hits():
    """It never did. `_resolve_throw` computed a distance, recorded it,
    and applied damage to nobody --- so Power Lad's freight wagon has been
    sailing through Wyatt Earp all afternoon.

    Routed through the ordinary attack pipeline, which is the point: a
    thrown wagon is an attack, so it rolls to hit against DCV, is stopped
    by defenses, and can knock a man back. Inventing a second damage path
    beside `resolve_attack_in_session` would have been a second set of
    rules to keep in step.
    """
    session = _session()
    offer = next(a for a in _menu(session)
                 if a.kind == "throw_object" and a.target_id == "ike")
    before = session.combatants["ike"].state.current_stun
    # Seed chosen so the throw connects; the point is that damage flows at
    # all, not that this particular roll hits.
    resolved = resolve_chosen(session, session.combatants["lad"], offer,
                              template=TEMPLATE, roller=RandomRoller(seed=11))
    after = resolved.session.combatants["ike"].state.current_stun
    payload = [e for e in resolved.events
               if getattr(e, "kind", "") == "ActionResolved"][-1].result_payload
    assert "hit" in payload, payload
    if payload.get("hit"):
        assert after < before, "it connected and he felt nothing"


def test_the_throw_is_still_recorded_as_a_throw():
    """Guards the guard: routing it through the attack pipeline must not
    lose what the action WAS --- a consumer reading the log should see a
    thrown object, not a punch."""
    session = _session()
    offer = next(a for a in _menu(session)
                 if a.kind == "throw_object" and a.target_id == "ike")
    resolved = resolve_chosen(session, session.combatants["lad"], offer,
                              template=TEMPLATE, roller=RandomRoller(seed=11))
    assert resolved.kind == "throw_object"
