"""A Darkness field is in the record, so a fight rebuilt from it keeps it (6E1 p.188).

`Darkness.place` put the zone on `session.scene.constructs` IN PLACE and
logged a `ConstructSpawned` beside it, which `apply_event` treats as
audit-only. Anything that rebuilds the fight from its rows --- kirby-api
does it at EVERY Phase, and `rewind_to_sequence` and a Krackle replay do it
too --- started from the authored Scene and had no field. Found live
2026-11-11 (local fight 35de6a41): Talisman cast Darkness at 14/30 STUN,
the zone was gone by the next Phase, and the D-Soldiers she meant to blind
shot her unconscious through it.

The same defect, and the same cure, as the Force Wall
(`tests/loop/test_a_force_wall_survives_the_replay.py`): `DarknessPlaced`
is the event, and `apply_event` is what puts the field on the board.
"""
from __future__ import annotations

from kirby_dice import FakeRoller
from test_darkness import EAST, WEST, _blocked, _session

from kirby_combat.actions.darkness import Darkness
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.rewind import rewind_to_sequence

BOX = [(8.0, 0.0), (12.0, 0.0), (12.0, 10.0), (8.0, 10.0)]


def _placed(*, sense_groups=("sight",), personal_immunity=False) -> CombatSession:
    s = _session(WEST, EAST, [], roller=FakeRoller([[3, 3, 3]]))
    s, result = Darkness.place(
        s, attacker_id="boz", polygon_xy=BOX, elevation_range_m=(0.0, 3.0),
        sense_groups=list(sense_groups), personal_immunity=personal_immunity,
    )
    assert result.hit
    return s


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


def _zones(session: CombatSession):
    return sorted(
        (c.obj_id, tuple(map(tuple, c.polygon_xy)), tuple(c.elevation_range_m),
         c.sense_group, c.creator_immune, c.source_combatant_id)
        for c in session.scene.constructs if c.kind == "darkness_zone"
    )


def test_the_field_is_an_event():
    session = _placed()
    (placed,) = [e for e in session.event_log if e.kind == "DarknessPlaced"]
    assert [tuple(p) for p in placed.polygon_xy] == BOX
    assert tuple(placed.elevation_range_m) == (0.0, 3.0)
    assert placed.sense_group == "sight"
    assert placed.creator_immune is False
    assert placed.source_combatant == "boz"


def test_a_replay_from_the_log_has_the_field():
    session = _placed()
    live = _zones(session)
    assert live, "the field must reach the live board"
    assert _zones(_replayed(session)) == live


def test_a_replay_still_blinds():
    """The point of the field, after a rebuild: ana cannot see boz through it."""
    assert _blocked(_replayed(_placed())) is True


def test_a_replay_keeps_one_field_per_sense_group_and_the_immunity():
    session = _placed(sense_groups=("sight", "hearing"), personal_immunity=True)
    assert len(_zones(session)) == 2
    assert _zones(_replayed(session)) == _zones(session)


def test_rewinding_past_the_field_takes_it_away():
    session = _placed()
    (placed,) = [e for e in session.event_log if e.kind == "DarknessPlaced"]
    before = rewind_to_sequence(session, placed.sequence - 1)
    assert before.scene.constructs == []


def test_placing_leaves_the_authored_scene_alone():
    """The in-place write also leaked the field into the authored Scene."""
    session = _placed()
    assert session.initial_scene.constructs == []
