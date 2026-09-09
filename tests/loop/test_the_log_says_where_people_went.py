"""A fight records that somebody moved.

`MovementResolved` is defined in `session/events.py`, exported from the
package, listed in the event union, handled by `apply_event`, covered by a
serialization round-trip test -- and the LOOP has never emitted one.

There are two movement paths and only one of them logs.
`MovementAction.resolve` (actions/movement/base.py) builds the event; the
loop's resolvers -- `move_to_cover`, `disengage`, every `reposition` --
go through `placement.move_toward` -> `placement.commit_move`, which
writes the new position onto the Scene and says nothing.

MEASURED, and it is why this was found: a recording of the O.K. Corral
made for the Krackle replay contains 22 ActionDeclared, 22 ActionResolved,
8 of which are movement -- and ZERO MovementResolved. PeterB, watching it:
"no one is moving". The renderer had no way to know they had. The
reference recording made through kirby-api, which uses the other path, has
thirteen.

`commit_move` is the right place: its own docstring calls it the moment a
landing is "written onto the Scene", and it is the single choke point that
`move_toward` and every loop resolver funnel through. Emitting anywhere
further out would mean four call sites agreeing about what a move is.
"""
from __future__ import annotations

from conftest import fighter                        # tests/loop/conftest.py
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


def _session():
    scene = Scene(
        id="lot", name="lot",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 20.0, 20.0, 14.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-2, -2), (20, -2), (20, 20), (-2, 20)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={"tom": Position(0.0, 0.0, 0.0),
                             "virgil": Position(10.0, 0.0, 0.0)},
    )
    return CombatSession.create(
        id="s", scene=scene, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=3),
        combatants=[fighter("tom", side=Side.named("cow")),
                    fighter("virgil", side=Side.named("law"))],
    ).start()


def _moves(session):
    return [e for e in session.event_log
            if getattr(e, "kind", "") == "MovementResolved"]


def test_moving_somebody_records_it():
    from kirby_combat.scene.placement import move_toward

    session = _session()
    assert _moves(session) == []
    session, outcome = move_toward(session, "tom", Position(4.0, 0.0, 0.0),
                                   mode="running", distance_m=6.0)
    events = _moves(session)
    assert len(events) == 1, "a move that happened must appear in the log"
    assert events[0].combatant_id == "tom"


def test_it_records_where_from_and_where_to():
    """A replay draws the glide between the two, so both ends matter."""
    from kirby_combat.scene.placement import move_toward

    session = _session()
    session, _ = move_toward(session, "tom", Position(4.0, 0.0, 0.0),
                             mode="running", distance_m=6.0)
    event = _moves(session)[0]
    assert event.from_pos["x"] == 0.0
    assert event.to_pos["x"] == 4.0


def test_standing_still_is_not_a_move():
    """A refusal lands the mover back where they started, and a log full of
    zero-length moves is noise a replay would animate."""
    from kirby_combat.scene.placement import move_toward

    session = _session()
    session, _ = move_toward(session, "tom", Position(0.0, 0.0, 0.0),
                             mode="running", distance_m=6.0)
    assert _moves(session) == []


def test_a_whole_fight_records_its_movement():
    """The end of the chain: the loop's own resolvers, not `move_toward`
    called by hand."""
    import kirby_combat.loop.resolvers  # noqa: F401 -- registers the kinds
    from kirby_combat.enumeration import enumerate_actions
    from kirby_combat.loop.registry import resolve_chosen

    session = _session()
    menu = enumerate_actions(
        session.combatants["tom"], [session.combatants["virgil"]],
        has_scene=True, scene=session.scene,
    )
    move = next((m for m in menu if m.kind == "move"), None)
    assert move is not None, f"no move offered; kinds were {sorted({m.kind for m in menu})}"
    out = resolve_chosen(session, session.combatants["tom"], move,
                         template=CombatTemplate.default_6e_superheroic(),
                         roller=RandomRoller(seed=3))
    assert _moves(out.session), "the loop moved him and logged nothing"
