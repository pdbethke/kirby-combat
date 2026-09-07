"""The Images resolver, reconnected — the clearest orphan of the set.

`kirby_combat/actions/images.py` is 480 lines whose ONLY importer, until
2026-09-06, was its own test file. No production caller anywhere: the
parked kirby-api driver re-derived the placement itself in
`_resolve_create_image_decoy`, so the engine's version sat unreachable
behind a permanently green suite.

It stayed unreachable one step longer than the mental resolvers, and for a
real reason rather than an oversight: `Images.place` needs a POSITION, and
the loop did not read `CombatSession.scene` at all. Plumbing the scene
through unblocked it.

WHAT IS RAW AND WHAT IS JUDGEMENT, kept separate on purpose. 6E1 p.238
governs whether an Image is CREATED (an Attack Roll against DCV 3) and
whether it is BELIEVED (a PER Roll to disbelieve) -- all of that is
`Images.place`, untouched. It says nothing about WHERE a caster puts one,
so `_decoy_position` is a judgement, and is labelled as one.
"""
from __future__ import annotations

import pytest

from conftest import fighter  # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop import registered_kinds
from kirby_combat.loop.registry import (
    DECOY_STANDOFF_M, UnresolvableAction, _decoy_position, resolve_chosen,
)
from kirby_combat.scene.scene import AmbientConditions, Position, Scene, SceneBounds
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


class _ImagesPower:
    """An IMAGES power in the shape `images_power` and `images_groups` read."""
    xmlid = "IMAGES"
    name = "Phantasm"
    levels = 5
    option_id = None
    assigned_adders: list = []


def _caster(id: str, side: str):
    c = fighter(id, side=Side.named(side), dex=20)
    c.hero.powers = [_ImagesPower()]
    return c


def _scene(**positions: Position) -> Scene:
    return Scene(
        id="street", name="A Street",
        bounds=SceneBounds(0, 0, 0, 200, 200, 50),
        surfaces=[], walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions=dict(positions),
    )


def _session(scene: Scene | None):
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE, dice_roller=RandomRoller(seed=5),
        combatants=[_caster("caster", "heroes"),
                    fighter("mark", side=Side.named("villains")),
                    fighter("distant", side=Side.named("villains"))],
    ).start()


ACTION = LegalAction(
    action_id="image_decoy:src", kind="image_decoy", target_id=None,
    power_xmlid="IMAGES", power_name="Phantasm",
    summary="Conjure an Image decoy near the nearest enemy",
)


# ---- It is reachable at all ----

def test_image_decoy_is_registered():
    assert "image_decoy" in registered_kinds()


def test_the_engine_places_a_decoy_and_records_it():
    session = _session(_scene(
        caster=Position(0.0, 0.0, 0.0),
        mark=Position(10.0, 0.0, 0.0),
        distant=Position(90.0, 0.0, 0.0),
    ))
    resolved = resolve_chosen(
        session, session.combatants["caster"], ACTION,
        template=TEMPLATE, roller=RandomRoller(seed=5),
    )
    assert resolved.kind == "image_decoy"
    assert resolved.events, "the placement must reach the log"


# ---- Placement: a judgement, pinned so it cannot drift silently ----

def test_the_decoy_stands_between_the_caster_and_the_NEAREST_enemy():
    session = _session(_scene(
        caster=Position(0.0, 0.0, 0.0),
        mark=Position(10.0, 0.0, 0.0),
        distant=Position(90.0, 0.0, 0.0),
    ))
    x, y, z = _decoy_position(session, session.combatants["caster"])
    assert (x, y, z) == pytest.approx((10.0 - DECOY_STANDOFF_M, 0.0, 0.0))


def test_the_nearest_enemy_is_chosen_whichever_order_they_are_in():
    session = _session(_scene(
        caster=Position(0.0, 0.0, 0.0),
        mark=Position(90.0, 0.0, 0.0),
        distant=Position(10.0, 0.0, 0.0),
    ))
    x, _, _ = _decoy_position(session, session.combatants["caster"])
    assert x == pytest.approx(10.0 - DECOY_STANDOFF_M)


def test_height_is_carried_not_flattened():
    session = _session(_scene(
        caster=Position(0.0, 0.0, 0.0),
        mark=Position(0.0, 0.0, 10.0),
        distant=Position(90.0, 0.0, 0.0),
    ))
    _, _, z = _decoy_position(session, session.combatants["caster"])
    assert z == pytest.approx(10.0 - DECOY_STANDOFF_M), "a rooftop decoy stays up"


def test_nose_to_nose_puts_the_decoy_on_the_enemy_not_behind_the_caster():
    """Stepping DECOY_STANDOFF_M back from an enemy who is already closer
    than that would place the decoy behind the caster."""
    session = _session(_scene(
        caster=Position(0.0, 0.0, 0.0),
        mark=Position(1.0, 0.0, 0.0),
        distant=Position(90.0, 0.0, 0.0),
    ))
    x, _, _ = _decoy_position(session, session.combatants["caster"])
    assert x == pytest.approx(1.0)


# ---- It refuses rather than guessing ----

def test_no_scene_refuses_rather_than_inventing_a_coordinate():
    session = _session(None)
    with pytest.raises(UnresolvableAction, match="image_decoy"):
        resolve_chosen(
            session, session.combatants["caster"], ACTION,
            template=TEMPLATE, roller=RandomRoller(seed=5),
        )


def test_a_caster_not_on_the_map_refuses():
    session = _session(_scene(mark=Position(10.0, 0.0, 0.0)))
    assert _decoy_position(session, session.combatants["caster"]) is None


def test_no_enemy_on_the_map_refuses():
    session = _session(_scene(caster=Position(0.0, 0.0, 0.0)))
    assert _decoy_position(session, session.combatants["caster"]) is None


def test_a_caster_without_an_images_power_refuses():
    session = _session(_scene(
        caster=Position(0.0, 0.0, 0.0), mark=Position(10.0, 0.0, 0.0),
    ))
    plain = session.combatants["mark"]      # no IMAGES power
    session.combatants["mark"].hero.powers = []
    with pytest.raises(UnresolvableAction, match="image_decoy"):
        resolve_chosen(
            session, plain, ACTION, template=TEMPLATE, roller=RandomRoller(seed=5),
        )


# ---- Sense groups come off the power, as Flash and Darkness do ----

def test_the_decoy_defaults_to_the_sight_group():
    from kirby_combat.perception import images_groups

    assert images_groups(_ImagesPower()) == frozenset({"sight"})
