"""A Force Wall is in the record, so a replay has it (6E1 p.167).

`_resolve_force_wall` appended the `Wall` to `session.scene.walls` IN PLACE
and logged an `ActionResolved` beside it. A fight rebuilt from its rows ---
which is what kirby-api does, and what `rewind_to_sequence` and a Krackle
replay do --- starts from the authored Scene and replays the log, so the
wall was simply not there: the shot it was raised to stop went through on
the replay. `BarrierRaised` is the event, and `apply_event` is what puts the
wall on the board.
"""
from __future__ import annotations

from conftest import fighter                             # tests/loop/conftest.py
from kirby_dice import RandomRoller

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.scene.scene import AmbientConditions, Position, Scene, SceneBounds
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.rewind import rewind_to_sequence
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()


class _Barrier:
    xmlid = "FORCEWALL"
    name = "Force Wall"
    levels = 6
    id = "fw-1"


def _raised():
    scene = Scene(
        id="s", name="S", bounds=SceneBounds(0, 0, 0, 100, 100, 50),
        surfaces=[], walls=[], hazards=[], ambient=AmbientConditions(),
        combatant_positions={
            "wall-man": Position(0.0, 0.0, 0.0), "mark": Position(20.0, 0.0, 0.0),
        },
    )
    session = CombatSession.create(
        id="s", scene=scene, template=TEMPLATE, dice_roller=RandomRoller(seed=9),
        combatants=[fighter("wall-man", side=Side.named("heroes")),
                    fighter("mark", side=Side.named("villains"))],
    ).start()
    action = LegalAction(
        action_id="force_wall:fw-1", kind="force_wall", target_id=None,
        power_xmlid="FORCEWALL", power_name="Force Wall", summary="wall",
        _attack_view=_Barrier(),
    )
    return resolve_chosen(
        session, session.combatants["wall-man"], action,
        template=TEMPLATE, roller=RandomRoller(seed=9),
    ).session


def _replayed(session: CombatSession) -> CombatSession:
    """What a consumer that persisted the rows rebuilds: the authored board,
    then every event, through the one door."""
    fresh = CombatSession.create(
        id=session.id, combatants=list(session.initial_combatants.values()),
        scene=session.initial_scene.snapshot(), template=session.template,
        dice_roller=session.dice_roller,
    )
    for event in session.event_log:
        fresh = apply_event(fresh, event)
    return fresh


def test_the_wall_is_an_event():
    session = _raised()
    (raised,) = [e for e in session.event_log if e.kind == "BarrierRaised"]
    assert raised.body == 6 and raised.def_value == 6 and raised.ed_value == 6
    assert raised.source_combatant == "wall-man"


def test_a_replay_from_the_log_has_the_wall():
    session = _raised()
    live = [(w.id, w.segment, w.body) for w in session.scene.walls]
    assert live, "the wall must reach the live board"
    assert [(w.id, w.segment, w.body) for w in _replayed(session).scene.walls] == live


def test_rewinding_past_the_wall_takes_it_down():
    session = _raised()
    (raised,) = [e for e in session.event_log if e.kind == "BarrierRaised"]
    before = rewind_to_sequence(session, raised.sequence - 1)
    assert before.scene.walls == []
