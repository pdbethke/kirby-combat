"""`smash_cover` names the WALL, and only when there is one.

MEASURED at the O.K. Corral: of 142 fall-throughs over 25 seeded runs, 50
were `smash_cover` alone --- it produced a plan every single Phase and the
plan was never executable.

Two defects, both of which the tactic's own prose already contradicts.

ONE: it named a PERSON. `attack_construct` offers are keyed by the id of
the WALL (`attack:construct:flys-studio:...`), so `target_id=virgil_earp`
matched no offer, ever. The tactic that exists to shoot the wall named the
man --- the mirror of the bug the file already documents in its own
comment, where it named the right man with the wrong kind.

TWO: `applicable` asked only "does the actor have a damaging attack",
which is true of essentially everybody with a gun. So the tactic whose
basis is "cover the enemy is using is worth more destroyed than ignored"
fired when no enemy was using any cover, at priority 35, ahead of tactics
that would have shot somebody.

The engine already knows which wall screens whom: `perceive` returns
`occluder_id`, "the REAL id of the nearest blocking wall". Read it.

That makes construct attacks DELIBERATE. Once `ordered_menu` put scenery
at the bottom, the benchmark's 43 accidental shots at buildings went to 0;
this is how a fighter shoots one on purpose --- because Virgil is behind
it and the wall is the way through.

Lives beside the loop fixtures because it needs real combatants with real
positions in a real scene; the perception gate cannot be asked about a
stub.
"""
from __future__ import annotations

from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.tactics.base import Situation
from kirby_combat.tactics.catalog.smash_cover import SmashCover
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

STUDIO = "flys-studio"


def _scene(walls, **positions):
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 14.0, 14.0, 14.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (14, -2), (14, 14), (-2, 14)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=list(walls), hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={k: Position(*v, 0.0) for k, v in positions.items()},
    )


def _studio():
    return _wall_of(def_value=4, body=8)


def _wall_of(*, def_value, body, resistant=True):
    return Wall(id=STUDIO, name="Fly's Studio",
                segment=(Position(5.0, 0.0, 0.0), Position(5.0, 10.0, 0.0)),
                height_m=6.0, blocks_los=True, blocks_movement=True,
                cover_level=4, body=body, def_value=def_value,
                resistant=resistant)


def _gun(*, dice, killing=False, minus_one=False):
    """One weapon, built rather than mutated in -- `attacks` is a
    read-only property derived from the build."""
    from kirby_combat.models import AttackPower

    return AttackPower(
        xmlid="RKA" if killing else "ENERGYBLAST", name="gun",
        damage_dice=dice, half_die=False, plus_one=False,
        damage_type="killing" if killing else "normal",
        defense_type="pd", range_m=100.0, uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        is_ranged=True, minus_one=minus_one, source_id="gun")


def _situation(scene, *, gun=None):
    from fixtures.synthetic_hero import synthetic_combatant

    tom = (fighter("tom", side=Side.named("cow")) if gun is None
           else synthetic_combatant(
               id="tom", name="tom", ocv=9, dcv=5, omcv=5, dmcv=5, spd=4,
               dex=20, ego=15, str_=15, con=18, pre=15, rec=6, pd=4, ed=4,
               rpd=2, red=2, md=3, power_defense=0, flash_defense=0,
               max_stun=40, max_body=12, max_end=40, current_stun=40,
               current_body=12, current_end=40, side=Side.named("cow"),
               attacks=[gun]))
    session = CombatSession.create(
        id="s", scene=scene, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=5),
        combatants=[tom, fighter("virgil", side=Side.named("law"))],
    ).start()
    return Situation(actor=session.combatants["tom"], allies=[],
                     enemies=[session.combatants["virgil"]],
                     current_segment=12, turn=1, session=session)


def test_the_plan_names_the_wall_not_the_man():
    situation = _situation(_scene([_studio()], tom=(2.0, 5.0), virgil=(9.0, 5.0)))
    assert [s.target_id for s in SmashCover().execute(situation).steps] == [STUDIO]


def test_it_applies_when_somebody_is_behind_something():
    situation = _situation(_scene([_studio()], tom=(2.0, 5.0), virgil=(9.0, 5.0)))
    assert SmashCover().applicable(situation) is True


def test_it_does_not_apply_when_nobody_is():
    """An enemy standing in the open has no cover to smash. This fired
    every Phase of every fight regardless."""
    situation = _situation(_scene([], tom=(2.0, 5.0), virgil=(9.0, 5.0)))
    assert SmashCover().applicable(situation) is False


def test_a_wall_that_screens_nobody_is_not_a_target():
    """The studio is on the map, but both men are north of it with a clear
    line between them."""
    situation = _situation(_scene([_studio()], tom=(2.0, 12.0), virgil=(9.0, 12.0)))
    assert SmashCover().applicable(situation) is False


def test_no_scene_means_no_cover_to_smash():
    """Most fights have no map, and there is no wall to name in a void."""
    session = CombatSession.create(
        id="s", scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter("tom", side=Side.named("cow")),
                    fighter("virgil", side=Side.named("law"))],
    ).start()
    situation = Situation(actor=session.combatants["tom"], allies=[],
                          enemies=[session.combatants["virgil"]],
                          current_segment=12, turn=1, session=session)
    assert SmashCover().applicable(situation) is False


# ---- You cannot shoot down a saloon ----

def test_a_wall_your_gun_cannot_dent_is_not_worth_shooting():
    """THE ARITHMETIC, not a judgement call.

    A 1d6-1 killing attack averages 2.5 BODY. A resistant DEF 4 wall takes
    none of it (6E2 p.172), so the shot is not slow, it is futile -- only a
    natural 6 does anything at all, 1 BODY, which against 8 is 48 shots.

    NOT THE CORRAL'S COLT. The Colt Peacemaker is RKA `LEVELS=1 +
    MINUSONEPIP`, which is one die ADDED to the base -- 2d6-1, averaging 6
    BODY, so it puts 2 through DEF 4 and takes the Harwood House's wall in
    four shots. The gun here is a weaker one built for this test. Said
    plainly because an earlier reading of this file had the Colt at 1d6-1
    and drew the opposite conclusion from it.

    A tactic whose basis is "cover the enemy is using is worth more
    destroyed than ignored" is simply WRONG when the cover cannot be
    destroyed, and the engine can prove which case it is in.
    """
    situation = _situation(
        _scene([_wall_of(def_value=4, body=8)], tom=(2.0, 5.0), virgil=(9.0, 5.0)),
        gun=_gun(dice=1, minus_one=True, killing=True),   # the Colt Peacemaker
    )
    assert SmashCover().applicable(situation) is False


def test_a_wall_your_gun_can_chew_through_is():
    """2d6 killing: 7 BODY average, 3 through DEF 4, three Phases to the
    wall. That is a real plan, and it is roughly what everyone at the
    O.K. Corral is actually carrying."""
    situation = _situation(
        _scene([_wall_of(def_value=4, body=8)], tom=(2.0, 5.0), virgil=(9.0, 5.0)),
        gun=_gun(dice=2, killing=True),                   # a shotgun
    )
    assert SmashCover().applicable(situation) is True


def test_a_killing_attack_ignores_NON_resistant_defense():
    """6E2 p.173: a defense the Objects Table prints in parentheses is
    Normal Defense and does not apply against Killing damage. Glass is
    (1)/(1)/1. The weak gun that cannot scratch a resistant wall goes
    straight through a window."""
    situation = _situation(
        _scene([_wall_of(def_value=4, body=8, resistant=False)],
               tom=(2.0, 5.0), virgil=(9.0, 5.0)),
        gun=_gun(dice=1, minus_one=True, killing=True),
    )
    assert SmashCover().applicable(situation) is True
