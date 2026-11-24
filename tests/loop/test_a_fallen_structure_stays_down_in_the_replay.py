"""A structure brought down stays down when the fight is replayed.

Found by the replay-parity sweep (two-databases spec §6 R1, 2026-11-24) in
`examples/the_shootout_we_can_publish.py`, seed 5: the crates were shot to
pieces and left the board in the fight that ran, and stood back up in the
fight rebuilt from its log. `bring_it_down` took them off the board in
place, and the only row about it was the shot's `ActionResolved`, which
`apply_event` treats as an outcome and folds nothing from.

Same defect, same cure, as the Darkness field and the Force Wall:
`StructureBroughtDown` is the event, and `apply_event` is what changes the
board. All three outcomes go through it: a smash (gone), a breach (a hole:
no longer blocks sight, still blocks movement), a collapse (gone, and it
falls on whoever is under it, which rides on its own `VitalsChanged`).
"""
from __future__ import annotations

from test_a_hole_is_not_a_demolition import (
    _building, _session, _wall, _wall_named,
)

from kirby_combat.collapse import bring_it_down
from kirby_combat.session.parity import divergence
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


def _down(session, target):
    return bring_it_down(session, target, roller=RandomRoller(seed=5),
                         template=CombatTemplate.default_6e_superheroic(),
                         caused_by="tom")


def _the_row(session):
    (row,) = [e for e in session.event_log if e.kind == "StructureBroughtDown"]
    return row


def test_a_smashed_stack_of_barrels_stays_gone():
    barrels = _wall(id="barrels", name="Stack of whiskey barrels",
                    height_m=1.2, cover_level=2, body=4, def_value=2,
                    blocks_los=False)
    session = _session([barrels], [], tom=(6.0, 5.0), ike=(-1.0, 5.0))
    session, _ = _down(session, _wall_named(session, "barrels"))
    row = _the_row(session)
    assert (row.construct_id, row.outcome) == ("barrels", "smashed")
    assert _wall_named(session, "barrels") is None
    assert divergence(session) == []


def test_a_hole_in_a_wall_is_still_a_hole():
    session = _session([_wall(part_of="harwood-interior")], [_building()],
                       tom=(2.0, 5.0), ike=(-1.0, 5.0))
    session, _ = _down(session, _wall_named(session, "harwood"))
    assert _the_row(session).outcome == "breached"
    assert _wall_named(session, "harwood").blocks_los is False
    assert divergence(session) == []


def test_a_fallen_building_stays_fallen_and_its_victims_stay_hurt():
    session = _session([], [_building()], tom=(6.0, 5.0), ike=(-1.0, 5.0))
    session, caught = _down(session, _building())
    assert _the_row(session).outcome == "collapsed"
    assert caught, "the man inside was under it"
    assert divergence(session) == []
