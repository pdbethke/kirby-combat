"""Hazard trigger detection tests."""
import pytest

from kirby_combat.scene import (
    Scene, SceneBounds, Hazard, HazardEffect, Position, AmbientConditions,
)
from kirby_combat.scene.hazards import (
    compute_hazard_triggers, HazardTriggerResult,
)


def _scene_with_fire(elevation_range=(0.0, 2.0), trigger="on_enter") -> Scene:
    fire = Hazard(
        id="fire1", name="Spreading Fire",
        polygon_xy=[(5, 5), (10, 5), (10, 10), (5, 10)],
        elevation_range_m=elevation_range,
        trigger=trigger,
        effect=HazardEffect(damage_dice=2, damage_type="energy"),
    )
    return Scene(
        id="s1", name="Burning Room",
        bounds=SceneBounds(0, 0, 0, 20, 20, 10),
        surfaces=[], walls=[], hazards=[fire],
        ambient=AmbientConditions(),
        combatant_positions={},
    )


# ---- on_enter ----

def test_on_enter_triggers_when_moving_into_polygon():
    s = _scene_with_fire(trigger="on_enter")
    before = {"alice": Position(0, 0, 0)}
    after = {"alice": Position(7, 7, 0)}    # now inside fire polygon
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=before,
        combatant_positions_after=after, phase="movement",
    )
    assert len(results) == 1
    assert results[0].hazard_id == "fire1"
    assert results[0].affected_combatants == ["alice"]
    assert results[0].trigger_reason == "entered"
    assert results[0].effect.damage_dice == 2


def test_on_enter_does_not_trigger_when_already_inside():
    s = _scene_with_fire(trigger="on_enter")
    before = {"alice": Position(7, 7, 0)}    # already inside
    after = {"alice": Position(8, 8, 0)}     # still inside, just moved
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=before,
        combatant_positions_after=after, phase="movement",
    )
    assert results == []


def test_on_enter_does_not_trigger_when_leaving():
    s = _scene_with_fire(trigger="on_enter")
    before = {"alice": Position(7, 7, 0)}
    after = {"alice": Position(15, 15, 0)}    # exited
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=before,
        combatant_positions_after=after, phase="movement",
    )
    assert results == []


# ---- on_pass ----

def test_on_pass_triggers_when_path_crosses_polygon():
    s = _scene_with_fire(trigger="on_pass")
    before = {"alice": Position(0, 7, 0)}    # west of polygon
    after = {"alice": Position(15, 7, 0)}    # east of polygon — path goes THROUGH
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=before,
        combatant_positions_after=after, phase="movement",
    )
    assert len(results) == 1
    assert results[0].trigger_reason == "passed_through"


def test_on_pass_triggers_on_entry_even_if_no_exit():
    s = _scene_with_fire(trigger="on_pass")
    before = {"alice": Position(0, 7, 0)}
    after = {"alice": Position(7, 7, 0)}     # ended inside
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=before,
        combatant_positions_after=after, phase="movement",
    )
    assert len(results) == 1


def test_on_pass_does_not_trigger_when_path_misses_polygon():
    s = _scene_with_fire(trigger="on_pass")
    before = {"alice": Position(0, 0, 0)}
    after = {"alice": Position(15, 0, 0)}    # path along y=0, polygon y∈[5,10]
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=before,
        combatant_positions_after=after, phase="movement",
    )
    assert results == []


# ---- every_segment ----

def test_every_segment_triggers_on_combatants_inside_during_tick():
    s = _scene_with_fire(trigger="every_segment")
    positions = {"alice": Position(7, 7, 0), "bob": Position(0, 0, 0)}
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=positions,
        combatant_positions_after=positions, phase="segment_tick",
    )
    assert len(results) == 1
    assert results[0].affected_combatants == ["alice"]
    assert results[0].trigger_reason == "in_zone_during_tick"


def test_every_segment_does_not_fire_during_movement_phase():
    s = _scene_with_fire(trigger="every_segment")
    positions = {"alice": Position(7, 7, 0)}
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=positions,
        combatant_positions_after=positions, phase="movement",
    )
    assert results == []


# ---- elevation filter ----

def test_elevation_range_excludes_flying_combatant():
    s = _scene_with_fire(elevation_range=(0.0, 2.0), trigger="on_enter")
    before = {"alice": Position(0, 0, 10)}     # 10m up
    after = {"alice": Position(7, 7, 10)}      # over the fire but at z=10
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=before,
        combatant_positions_after=after, phase="movement",
    )
    assert results == []


def test_elevation_range_includes_combatant_in_range():
    s = _scene_with_fire(elevation_range=(0.0, 5.0), trigger="on_enter")
    before = {"alice": Position(0, 0, 3)}
    after = {"alice": Position(7, 7, 3)}       # at z=3, within (0,5)
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=before,
        combatant_positions_after=after, phase="movement",
    )
    assert len(results) == 1


# ---- multiple combatants ----

def test_multiple_combatants_inside_one_hazard_combined_in_one_result():
    s = _scene_with_fire(trigger="every_segment")
    positions = {
        "alice": Position(6, 6, 0),
        "bob": Position(8, 8, 0),
        "carol": Position(0, 0, 0),    # outside
    }
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=positions,
        combatant_positions_after=positions, phase="segment_tick",
    )
    assert len(results) == 1     # one hazard → one result
    assert set(results[0].affected_combatants) == {"alice", "bob"}


# ---- effect propagation ----

def test_hazard_with_status_inflicted_propagates_in_effect():
    fire = Hazard(
        id="fire1", name="Magical Fire",
        polygon_xy=[(5, 5), (10, 5), (10, 10), (5, 10)],
        elevation_range_m=(0.0, 5.0),
        trigger="on_enter",
        effect=HazardEffect(damage_dice=3, damage_type="energy", status_inflicted="on_fire"),
    )
    s = Scene(
        id="s1", name="Magic Room",
        bounds=SceneBounds(0, 0, 0, 20, 20, 10),
        surfaces=[], walls=[], hazards=[fire],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    before = {"alice": Position(0, 0, 0)}
    after = {"alice": Position(7, 7, 0)}
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=before,
        combatant_positions_after=after, phase="movement",
    )
    assert len(results) == 1
    assert results[0].effect.damage_dice == 3
    assert results[0].effect.status_inflicted == "on_fire"


# ---- multiple hazards ----

def test_multiple_hazards_each_produce_their_own_result():
    fire = Hazard(
        id="fire", name="Fire",
        polygon_xy=[(5, 5), (10, 5), (10, 10), (5, 10)],
        elevation_range_m=(0.0, 5.0), trigger="on_enter",
        effect=HazardEffect(damage_dice=2, damage_type="energy"),
    )
    spikes = Hazard(
        id="spikes", name="Spike Pit",
        polygon_xy=[(15, 5), (18, 5), (18, 10), (15, 10)],
        elevation_range_m=(0.0, 5.0), trigger="on_enter",
        effect=HazardEffect(damage_dice=4, damage_type="killing"),
    )
    s = Scene(
        id="s1", name="Trap Room",
        bounds=SceneBounds(0, 0, 0, 20, 20, 10),
        surfaces=[], walls=[], hazards=[fire, spikes],
        ambient=AmbientConditions(),
        combatant_positions={},
    )
    before = {"alice": Position(0, 0, 0), "bob": Position(20, 0, 0)}
    after = {"alice": Position(7, 7, 0), "bob": Position(16, 7, 0)}
    results = compute_hazard_triggers(
        scene=s, combatant_positions_before=before,
        combatant_positions_after=after, phase="movement",
    )
    # Two hazards triggered, one by alice, one by bob
    assert len(results) == 2
    by_id = {r.hazard_id: r for r in results}
    assert by_id["fire"].affected_combatants == ["alice"]
    assert by_id["spikes"].affected_combatants == ["bob"]
