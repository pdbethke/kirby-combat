"""The loop reads the Scene.

WHAT WAS WRONG. `CombatSession.scene` has always existed, and `run_phase`
never read it -- so `enumerate_actions` was called with `has_scene`
defaulting to False and every scene-dependent offer was silently absent
from every menu. A fight on a map enumerated as though it were in a void:
no movement, no cover, no attacking a construct, no Images.

Nothing caught it because a menu that is merely SHORTER is still a valid
menu. The loop ran, a chooser picked, the fight was decided -- with a
whole class of legal action missing and no error anywhere. These tests
compare the two menus so the difference cannot go quiet again.
"""
from __future__ import annotations

import pytest

from conftest import fighter, session_of  # tests/loop/conftest.py
from kirby_combat.encounter import Encounter
from kirby_combat.loop import FirstLegalChooser, run_phase
from kirby_combat.loop.run import distances_from
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _apart(metres: float) -> Scene:
    """Two combatants that far apart on an empty street."""
    return _scene(
        aurora=Position(0.0, 0.0, 0.0), nemesis=Position(metres, 0.0, 0.0),
    )


def _scene(**positions: Position) -> Scene:
    return Scene(
        id="street", name="A Street",
        bounds=SceneBounds(0, 0, 0, 200, 200, 50),
        surfaces=[], walls=[], hazards=[],
        ambient=AmbientConditions(),
        combatant_positions=dict(positions),
    )


def _session(scene: Scene | None):
    fighters = [
        fighter("aurora", side=Side.named("heroes"), dex=25),
        fighter("nemesis", side=Side.named("villains"), dex=15),
    ]
    return CombatSession.create(
        id="s", combatants=fighters, scene=scene, template=TEMPLATE,
        dice_roller=RandomRoller(seed=3),
    ).start()


def _menu_kinds(scene: Scene | None, *, apart: float = 20.0) -> set[str]:
    """The kinds offered to the first actor, with and without a map."""
    session = _session(scene)
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    roller = RandomRoller(seed=3)
    enc = enc.run_segment(roller=lambda: roller.roll_dice(3))

    seen: list[set[str]] = []

    class Spy:
        def choose(self, situation):
            seen.append({a.kind for a in situation.menu})
            return situation.menu[0].action_id

    run_phase(
        enc.sessions[0], Spy(), template=TEMPLATE, roller=roller,
        on_unresolvable="skip",
    )
    return seen[0]


# ---- distances_from ----

def test_distances_are_measured_from_the_scene():
    scene = _scene(
        aurora=Position(0.0, 0.0, 0.0), nemesis=Position(3.0, 4.0, 0.0),
    )
    session = _session(scene)
    actor = session.combatants["aurora"]
    out = distances_from(scene, actor, [session.combatants["nemesis"]])
    assert out == {"nemesis": 5.0}, "3-4-5 in the xy plane"


def test_no_scene_means_unknown_rather_than_empty():
    """`enumerate_actions` reads an unknown distance as 'scene-less, no
    gate'. Returning {} instead of None would claim every enemy is at an
    unknown-but-mapped range, which is a different statement."""
    session = _session(None)
    assert distances_from(None, session.combatants["aurora"], []) is None


def test_an_actor_absent_from_the_map_has_no_distances():
    scene = _scene(nemesis=Position(3.0, 4.0, 0.0))
    session = _session(scene)
    assert distances_from(
        scene, session.combatants["aurora"], [session.combatants["nemesis"]],
    ) is None


def test_a_target_absent_from_the_map_is_simply_not_measured():
    """Absent from the map is not the same as at range 0."""
    scene = _scene(aurora=Position(0.0, 0.0, 0.0))
    session = _session(scene)
    out = distances_from(
        scene, session.combatants["aurora"], [session.combatants["nemesis"]],
    )
    assert out == {}


def test_height_counts():
    scene = _scene(
        aurora=Position(0.0, 0.0, 0.0), nemesis=Position(0.0, 0.0, 12.0),
    )
    session = _session(scene)
    out = distances_from(
        scene, session.combatants["aurora"], [session.combatants["nemesis"]],
    )
    assert out == {"nemesis": 12.0}, "a rooftop is not adjacent to the street"


# ---- The menu actually changes ----

def test_a_scene_adds_movement():
    """Movement needs somewhere to move.

    At 20m only plain `move` appears; `move_by` and `move_through` are
    move-AND-attack maneuvers, so they wait until the target is reachable
    -- see the adjacency test below."""
    gained = _menu_kinds(_apart(20.0)) - _menu_kinds(None)
    assert "move" in gained, sorted(gained)


def test_the_move_and_attack_maneuvers_appear_when_they_could_land():
    gained = _menu_kinds(_apart(1.0)) - _menu_kinds(None)
    assert {"move", "move_by", "move_through"} <= gained, sorted(gained)


def test_a_scene_GATES_melee_that_a_void_offered_freely():
    """THE CORRECTNESS HALF, and the more important one. Without a map
    there are no distances, so `_melee_gate` returns "direct" for every
    enemy and hand-to-hand is offered unconditionally --- a scene-less
    fight let combatants punch each other from any range, and nothing
    complained, because a menu that is merely WRONGER is still a menu.
    """
    void = _menu_kinds(None)
    far = _menu_kinds(_apart(20.0))

    assert {"strike", "grab", "disarm", "trip"} <= void, (
        "the void offers melee unconditionally -- that is the defect"
    )
    assert not ({"strike", "grab", "disarm", "trip"} & far), (
        f"melee must be gated at 20m; still offered: {sorted(far)}"
    )


def test_the_same_melee_returns_when_adjacent():
    """Gated by distance, not removed: step into reach and it is back."""
    near = _menu_kinds(_apart(1.0))
    assert {"strike", "grab", "disarm", "trip"} <= near, sorted(near)


def test_a_ranged_attack_survives_the_gate():
    """A 100m Blast at 20m is legal and must still be offered.

    This is the one that caught a FIXTURE bug rather than an engine bug:
    `AttackPower.is_ranged` defaults to False and documents but does not
    enforce "True when range_m > 0", while `_is_melee` reads that field
    FIRST and only falls back to `range_m`. The test fixture set
    `range_m=100` and left `is_ranged` alone, so a Blast was classified
    hand-to-hand and the reach gate dropped it --- which looked exactly
    like the Scene plumbing breaking ranged attacks. The engine's real
    path (`hero_view.py`) derives the flag correctly.
    """
    assert "attack" in _menu_kinds(_apart(20.0))
    assert "attack" in _menu_kinds(_apart(120.0)), "beyond range is a penalty, not a bar"


def test_the_scene_less_menu_still_works():
    """A fight with no map is legal and must keep enumerating -- the scene
    is plumbed through, not required."""
    assert _menu_kinds(None), "a scene-less fight must still offer actions"


def test_a_phase_resolves_with_a_scene_present():
    session = _session(_scene(
        aurora=Position(0.0, 0.0, 0.0), nemesis=Position(10.0, 0.0, 0.0),
    ))
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    roller = RandomRoller(seed=3)
    enc = enc.run_segment(roller=lambda: roller.roll_dice(3))

    result = run_phase(
        enc.sessions[0], FirstLegalChooser(), template=TEMPLATE,
        roller=roller, on_unresolvable="skip",
    )
    assert result.actor_id == "aurora"
    assert result.action_id is not None
