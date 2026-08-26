"""A Scene is a place, not a fight — it can hold an Encounter, but need not.

Per Task 2 of the setting-hierarchy work: `Scene.encounter` inverts the old
containment (CombatSession.scene) so a place is constructible without any
fight owning it. 6E2 p.8, "COMBAT AND NONCOMBAT TIME": precise Segment-level
time is only tracked when a sequence needs it, so `encounter is None` is the
normal resting state of a place, not an omission.
"""
from __future__ import annotations

from dataclasses import replace

from kirby_combat.encounter import Encounter
from kirby_combat.scene import (
    AmbientConditions, Position, Scene, SceneBounds,
)


def _a_house() -> Scene:
    return Scene(
        id="house", name="Safehouse",
        bounds=SceneBounds(0, 0, 0, 20, 20, 4),
        surfaces=[],
        walls=[],
        hazards=[],
        ambient=AmbientConditions(),
    )


def test_a_house_with_occupants_and_no_encounter_is_a_valid_scene():
    """PeterB's case: a house, five occupants doing chores, no combat.
    6E2 p.8: precise time is only counted when a sequence needs it, so a
    place at rest has no clock at all."""
    house = _a_house()
    for i, who in enumerate(["ana", "ben", "cal", "dee", "eve"]):
        house = house.place_combatant(who, Position(float(i), 0.0, 0.0))

    assert house.encounter is None
    assert len(house.combatant_positions) == 5


def test_a_scene_can_hold_an_encounter():
    scene = _a_house()
    fighting = replace(scene, encounter=Encounter(id="e1"))
    assert fighting.encounter.segment == 12
