"""`reach.closes_on`: can a man, on this movement, END within reach of that
enemy this Phase?

6E2 p.56 sets the reach a hand-to-hand attack needs; the place says where a
move lands (`movement_reach`), and the landing is held to the reach
(`within_reach`) --- the question the Move By / Move Through gate asks of
Running (6E2 p.56 + p.72), asked for any mode. With no geometry to judge it
does not guess: it raises `NoGeometry`.
"""
from __future__ import annotations

import pytest
from kirby_combat.scene.scene import (
    AmbientConditions,
    Position,
    Scene,
    SceneBounds,
    Surface,
)
from kirby_world.movement_legality import MovementOutcome

from kirby_combat.reach import NoGeometry, closes_on


def _floor(**positions) -> Scene:
    return Scene(
        id="lot", name="lot", bounds=SceneBounds(-5, -5, -5, 60, 60, 30),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-5, -5), (60, -5), (60, 60), (-5, 60)],
                          elevation_m=0.0, surface_type="ground", cover_level=0,
                          is_supporting=True)],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={k: Position(*v) for k, v in positions.items()},
    )


def _ask(scene, mode, budget_m, reach_m=1.0):
    return closes_on(scene, "hero", "goon", mode=mode, budget_m=budget_m,
                     reach_m=reach_m, session=None)


def test_a_run_long_enough_closes():
    assert _ask(_floor(hero=(0, 0, 0), goon=(10, 0, 0)), "running", 12.0)


def test_a_run_too_short_does_not():
    assert not _ask(_floor(hero=(0, 0, 0), goon=(10, 0, 0)), "running", 5.0)


def test_running_cannot_climb_to_him_and_flight_can():
    scene = _floor(hero=(0, 0, 0), goon=(5, 0, 8))
    assert not _ask(scene, "running", 30.0)
    assert _ask(scene, "flight", 20.0)


def test_no_movement_closes_nothing():
    assert not _ask(_floor(hero=(0, 0, 0), goon=(10, 0, 0)), "running", 0.0)


def test_the_landing_is_held_to_his_reach(monkeypatch):
    """A move the place calls reachable that lands out of reach does not
    close: the landing, not the flag, is the question."""
    from kirby_combat import reach

    def far(mode, here, there, budget_m, scene, **kw):
        return MovementOutcome(reachable=True, landing=Position(0, 0, 0), fall=None)

    monkeypatch.setattr(reach, "_place_reach", far)
    assert not _ask(_floor(hero=(0, 0, 0), goon=(10, 0, 0)), "flight", 30.0)


@pytest.mark.parametrize("scene", [
    None, _floor(hero=(0, 0, 0)), _floor(goon=(1, 0, 0))],
    ids=["no-scene", "no-goon", "no-hero"])
def test_no_geometry_raises_rather_than_guessing(scene):
    with pytest.raises(NoGeometry):
        _ask(scene, "running", 12.0)


def test_the_move_by_gate_is_its_running_case(monkeypatch):
    """`charge_connects` asks `closes_on` (one copy of the question); its
    own fail-open contract for a scene with no positions stays its own."""
    from kirby_combat import reach
    from kirby_combat.actions.martial_offers import charge_connects

    asked = []

    def spy(scene, mover_id, target_id, **kw):
        asked.append((mover_id, target_id, kw["mode"], kw["budget_m"], kw["reach_m"]))
        return False

    monkeypatch.setattr(reach, "closes_on", spy)

    class _Actor:
        id = "hero"

    scene = _floor(hero=(0, 0, 0), goon=(3, 0, 0))
    assert charge_connects(_Actor(), "goon", scene=scene, budget_m=12.0,
                           reach_m=1.0) is False
    assert asked == [("hero", "goon", "running", 12.0, 1.0)]
    assert charge_connects(_Actor(), "goon", scene=_floor(hero=(0, 0, 0)),
                           budget_m=12.0, reach_m=1.0) is True
