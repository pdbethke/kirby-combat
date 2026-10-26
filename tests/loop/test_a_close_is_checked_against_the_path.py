"""A close-and-strike is offered only when the path lets him close.

WHAT A PROD FIGHT SHOWED (session 33bf8bee, 2026-10-26). Pulsar chose
`move_strike` at Brainchild three Phases running, and each time ended the
Phase standing where he began, `reached: false`, having struck nobody. The
long-standing "move_strike 0-for-9" defect.

THREE BLOCKS MADE THE OFFER ON STRAIGHT-LINE DISTANCE ALONE --- the attack,
maneuver and bare-STR blocks, through `_melee_gate` (distance <= reach +
Half Move) --- while the resolver walks the real path through
`movement_reach`, which stops at a wall. The one block that DOES walk the
path, the movement block, never ran in a real fight at all: it is gated on
a `movement=` parameter `run_phase` did not pass, so every fight got the
scene-without-movement fallback (an unchecked running half-move, whatever
the man could actually do --- a flier was never offered his Flight).

And the bare-hands and maneuver closes carried no attack, so a close that
did work struck nobody; and the close's own `MovementResolved` was missing
from the step's events.
"""
from __future__ import annotations

from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.encounter import Encounter
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.loop.run import distances_from
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _lot(*, wall: bool, b_at: float = 6.0):
    walls = [Wall(id="w", name="w", height_m=3.0, blocks_los=True, blocks_movement=True,
                  segment=(Position(3.0, -5.0, 0.0), Position(3.0, 5.0, 0.0)))] if wall else []
    scene = Scene(
        id="f", name="f", bounds=SceneBounds(-50, -50, 0.0, 50, 50, 10.0),
        surfaces=[Surface(id="g", name="g", polygon_xy=[(-50, -50), (50, -50), (50, 50), (-50, 50)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=walls, hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"a": Position(0.0, 0.0, 0.0), "b": Position(b_at, 0.0, 0.0)},
    )
    return CombatSession.create(
        id="s", scene=scene, template=TEMPLATE, dice_roller=RandomRoller(seed=2),
        combatants=[fighter("a", side=Side.named("x"), armed=False, dex=30),
                    fighter("b", side=Side.named("y"))],
    ).start()


def _menu(session):
    """As `run_phase` asks for it --- movement included."""
    a, b = session.combatants["a"], session.combatants["b"]
    return enumerate_actions(a, [b], has_scene=True, scene=session.scene,
                             distances=distances_from(session.scene, a, [b]),
                             movement=list(a.movement_view()))


def test_no_close_is_offered_through_a_wall():
    """Six metres apart, a Half Move of 6 and a 1 m reach: straight-line
    distance says he can close. A wall across the way says he cannot."""
    assert not [m for m in _menu(_lot(wall=True)) if m.kind == "move_strike"]


def test_a_bare_handed_close_lands_where_it_was_checked_and_strikes():
    session = _lot(wall=False)
    close = next(m for m in _menu(session) if m.kind == "move_strike")
    assert close._attack_view is not None, "a close with no attack strikes nobody"
    assert close.reposition_dest is not None

    resolved = resolve_chosen(session, session.combatants["a"], close,
                              template=TEMPLATE, roller=RandomRoller(seed=2))
    kinds = [e.kind for e in resolved.events]
    assert "MovementResolved" in kinds
    landed = resolved.session.scene.combatant_positions["a"]
    assert (landed.x, landed.y) == close.reposition_dest[:2]
    struck = [e.result_payload for e in resolved.events if e.kind == "ActionResolved"]
    assert any(p.get("target_id") == "b" for p in struck)


def test_a_step_toward_a_distant_enemy_is_offered():
    """Twenty metres off on open ground: one move cannot reach him, and a
    step toward him is still a step. Gating on "reaches him" offered none."""
    assert "move:b" in {m.action_id for m in _menu(_lot(wall=False, b_at=20.0))}


def test_the_loop_offers_the_movement_he_owns():
    """`run_phase` hands enumeration the actor's movement --- a flier sees
    his Flight, not only a run."""
    class _Flier:
        mode, combat_m = "flight", 20.0

    session = _lot(wall=False, b_at=20.0)
    a = session.combatants["a"]
    object.__setattr__(a, "movement_view", lambda: [_Flier()])

    seen = []

    class _Look:
        def choose(self, situation):
            seen.extend(m.action_id for m in situation.menu)
            return "dodge"

    run_phase(Encounter(id="e", turn=1, segment=12, sessions=[session]), _Look(),
              roller=RandomRoller(seed=4))
    assert "move:flight:b" in seen
