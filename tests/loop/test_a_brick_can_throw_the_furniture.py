"""He can pick up a wagon and throw it --- and could not.

PeterB: *"he can literally pick up a horse or a wagon and throw it. or
throw a wagon at a house that ike is hiding in and collapse it"* /
*"why is that not an option"*.

Because `pickup` filters constructs on `kind == "debris"`, and NOTHING IN
THIS ENGINE HAS EVER CREATED ONE. "debris" is not even a member of
`ConstructKind` --- the string appears in exactly two lines, both of them
the filter itself, and in no test. So `pickup` and `throw_object` are two
complete action kinds, with registered resolvers and enumeration offers,
that could never once fire. The eighth thing this week that is computed,
correct and delivered nowhere, and the largest.

The comment above the filter even states the rule it was enforcing:
"Non-debris constructs (walls / hazards / force_walls) are never offered
--- only spawned rubble is throwable." A whiskey barrel is not rubble and
never becomes any, so a brick standing over one has no way to lift it.

THE ARITHMETIC WAS ALREADY RIGHT. `_primary_lift_kg` is the cost engine's
own STR->lift, 25 * 2^(STR/5), so Power Lad at STR 40 lifts 6,400kg. A
loaded wagon is about a tonne. The gate was never the weight; it was that
nothing on a battlefield was ever a thing you could pick up.

PORTABLE IS A PROPERTY OF THE OBJECT, not a kind of object. A barrel is
not a special sort of wall and rubble is not a special sort of barrel ---
both are simply things light enough to lift, which is what the weight
gate already asks. So `Construct` gains `portable`, and `pickup` asks
that instead of guessing from `kind`.
"""
from __future__ import annotations

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.scene.construct import Construct
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)
from kirby_combat.side import Side


def _wagon(obj_id="wagon", at=(2.0, 2.0), body=6, portable=True):
    return Construct(
        obj_id=obj_id, kind="wall",
        segment=(Position(at[0], at[1], 0.0), Position(at[0], at[1], 0.0)),
        height_m=1.5, blocks_los=False, blocks_movement=False,
        cover_level=2, def_value=3, body=body, portable=portable,
    )


def _scene(*constructs, actor_at=(2.0, 1.5)):
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 12.0, 12.0, 12.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (12, -2), (12, 12), (-2, 12)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"lad": Position(*actor_at, 0.0),
                             "ike": Position(9.0, 9.0, 0.0)},
        constructs=list(constructs),
    )


def _brick(str_=40):
    """Power Lad, near enough: strong, armoured, and holding his claws.

    He carries an attack deliberately. A synthetic combatant with STR >= 5
    and NO attacks makes enumeration build a bare-STR strike view, and the
    synthetic hero's characteristics carry no ids, so `_power_action_id`
    refuses to name it. That is a fixture limitation --- a real build always
    has ids --- and not what this test is about.
    """
    from fixtures.synthetic_hero import synthetic_combatant
    from kirby_combat.models import AttackPower

    claws = AttackPower(
        xmlid="HKA", name="Rending", damage_dice=6, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=0.0, uses_str=True, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=False, reach_m=1.0,
        source_id="lad-hka",
    )
    return synthetic_combatant(
        id="lad", name="lad", ocv=8, dcv=6, omcv=5, dmcv=5, spd=4, dex=20,
        ego=10, str_=str_, con=20, pre=10, rec=8, pd=2, ed=2, rpd=25, red=20,
        md=0, power_defense=0, flash_defense=0,
        max_stun=40, max_body=10, max_end=40,
        current_stun=40, current_body=10, current_end=40,
        side=Side.solo("lad"), attacks=[claws],
    )


def _menu(scene, actor=None):
    actor = actor or _brick()
    return enumerate_actions(
        actor, [fighter("ike", side=Side.named("cow"))],
        has_scene=True, scene=scene,
        constructs=list(scene.constructs),
        movement=list(actor.movement_view()),
    )


def test_a_brick_standing_over_a_wagon_can_pick_it_up():
    menu = _menu(_scene(_wagon()))
    assert [a.action_id for a in menu if a.kind == "pickup"] == ["pickup:wagon"]


def test_the_scenery_that_is_not_portable_stays_put():
    """A house is not a thing you lift, however strong you are."""
    menu = _menu(_scene(_wagon("harwood", portable=False)))
    assert not [a for a in menu if a.kind == "pickup"]


def test_an_ordinary_man_cannot_lift_the_wagon():
    """The weight gate still bites --- STR 10 lifts 100kg, a wagon is a
    tonne. `_primary_lift_kg` is the cost engine's own curve."""
    menu = _menu(_scene(_wagon(body=20)), actor=_brick(str_=10))
    assert not [a for a in menu if a.kind == "pickup"]


def test_he_has_to_be_next_to_it():
    """Reach still applies: a wagon across the lot is not in his hands."""
    menu = _menu(_scene(_wagon(at=(11.0, 11.0))))
    assert not [a for a in menu if a.kind == "pickup"]
