"""Something can finally ask to go around the building.

PeterB, shown five men shooting at a boarding house: "why not just go
around the building".

BECAUSE NOTHING COULD ASK. `reposition_strike` --- spend a half-move
reaching a vantage with a clear line of fire, then shoot --- is fully
built: enumeration offers it on exactly the condition that matters (an
enemy whose `perceive` result is `occluded`), a resolver resolves it, and
`nearest_visible_point` precomputes the destination so no geometry is
recomputed downstream.

NOT ONE OF THE TWENTY-FOUR TACTICS EVER NAMED THAT KIND. The whole
subsystem was reachable only by a chooser that invented the action id
itself. So when Virgil Earp stood behind Fly's Studio where no Cowboy
could see him, doctrine's entire answer was `smash_cover` --- break the
building --- and when that produced an unexecutable plan everyone fell
through to the fallback and shot the scenery.

The first test here is the one that matters and the one that could not
have passed yesterday: SOME tactic names `reposition_strike`.
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
from kirby_combat.tactics.library import all_tactics


def GoAroundTheCover():
    """Looked up from the REGISTRY, never imported directly.

    `@register` fires on import, so a test that imports the class puts it
    in the catalogue itself and then passes whether or not the shipped
    catalogue includes it. The first version of this file did exactly
    that, and its proof was worthless.
    """
    found = [t for t in all_tactics() if t.name == "go_around_the_cover"]
    assert found, "go_around_the_cover is not in the shipped catalogue"
    return found[0]
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


def test_some_tactic_can_ask_to_reposition_and_fire():
    """The gap itself. `reposition_strike` was built, offered and resolved,
    and no doctrine in the catalogue could request it.

    Proved by removing it from the catalogue and re-running: 24 tactics,
    and the ones that apply to an occluded enemy emit only `attack`,
    `attack_construct` and `move_to_cover` -- shoot him (impossible),
    shoot the wall, or hide. Nothing that walks around.
    """
    situation = _situation()
    kinds = set()
    for tactic in all_tactics():
        try:
            if not tactic.applicable(situation):
                continue
            kinds |= {step.kind for step in tactic.execute(situation).steps}
        except Exception:                              # pragma: no cover
            continue
    assert "reposition_strike" in kinds, (
        "no tactic in the catalogue can ask to move to a clear vantage and "
        f"fire; the applicable tactics emit only {sorted(kinds)}"
    )


def _scene(walls, **positions):
    return Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-4.0, -2.0, 0.0, 14.0, 14.0, 14.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-4, -2), (14, -2), (14, 14), (-4, 14)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=list(walls), hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={k: Position(*v, 0.0) for k, v in positions.items()},
    )


def _studio():
    return Wall(id="flys-studio", name="Fly's Studio",
                segment=(Position(5.0, 0.0, 0.0), Position(5.0, 10.0, 0.0)),
                height_m=6.0, blocks_los=True, blocks_movement=True,
                cover_level=4, body=3, def_value=4, part_of="flys-interior")


def _situation(scene=None):
    scene = scene if scene is not None else _scene(
        [_studio()], tom=(2.0, 5.0), virgil=(9.0, 5.0))
    session = CombatSession.create(
        id="s", scene=scene, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter("tom", side=Side.named("cow")),
                    fighter("virgil", side=Side.named("law"))],
    ).start()
    return Situation(actor=session.combatants["tom"], allies=[],
                     enemies=[session.combatants["virgil"]],
                     current_segment=12, turn=1, session=session)


def test_it_applies_when_a_wall_is_in_the_way():
    assert GoAroundTheCover().applicable(_situation()) is True


def test_it_does_not_apply_when_you_can_already_see_him():
    """Nothing to go around."""
    clear = _scene([], tom=(2.0, 5.0), virgil=(9.0, 5.0))
    assert GoAroundTheCover().applicable(_situation(clear)) is False


def test_it_names_the_man_not_the_wall():
    """`reposition_strike` offers are keyed by the ENEMY --- you are moving
    to get a shot at him. The mirror of `smash_cover`, which names the
    wall because it is shooting the wall."""
    plan = GoAroundTheCover().execute(_situation())
    assert [(s.kind, s.target_id) for s in plan.steps] == [
        ("reposition_strike", "virgil")]


def test_going_around_outranks_breaking_through():
    """Walking round the end of a wall is cheaper than making a hole in
    it, so it is tried first. `smash_cover` is still the answer when there
    is no way around: enumeration offers no reposition then, and the
    chooser falls through to it."""
    assert GoAroundTheCover().priority > SmashCover().priority


def test_no_scene_means_no_wall_to_go_around():
    session = CombatSession.create(
        id="s", scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=5),
        combatants=[fighter("tom", side=Side.named("cow")),
                    fighter("virgil", side=Side.named("law"))],
    ).start()
    situation = Situation(actor=session.combatants["tom"], allies=[],
                          enemies=[session.combatants["virgil"]],
                          current_segment=12, turn=1, session=session)
    assert GoAroundTheCover().applicable(situation) is False
