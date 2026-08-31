"""The close-and-strike composite: close, then may the strike happen?

The defect this closes, observed in a live fight on 2026-08-31: Cheshire Cat
attempted a martial throw on GORGON while standing on a rooftop six metres
above him. The close was resolved scene-aware (and legally went nowhere, since
running is same-elevation only), and the strike resolved anyway.
"""
import pytest

from kirby_combat.actions.move_strike import (
    MoveStrikeOutcome, StrikePlan, resolve_move_strike,
)
from kirby_combat.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)


def _rooftop_arena() -> Scene:
    """Ground at z=0 over the whole floor; a rooftop at z=6 over x in [10,20]."""
    return Scene(
        id="arena", name="Urban Rooftop",
        bounds=SceneBounds(0, 0, 0, 20, 20, 20),
        surfaces=[
            Surface(id="ground", name="Ground",
                    polygon_xy=[(0, 0), (20, 0), (20, 20), (0, 20)],
                    elevation_m=0.0, surface_type="ground",
                    cover_level=0, is_supporting=True),
            Surface(id="roof", name="Roof",
                    polygon_xy=[(10, 0), (20, 0), (20, 20), (10, 20)],
                    elevation_m=6.0, surface_type="rooftop",
                    cover_level=0, is_supporting=True),
        ],
        walls=[],
        hazards=[],
        ambient=AmbientConditions(),
        combatant_positions={},
    )


def test_an_attacker_on_a_roof_cannot_reach_the_street_below():
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(15, 10, 6),      # on the rooftop
        target_pos=Position(15, 10, 0),     # directly below, on the street
        mode="running",
        half_move_m=6.0,                    # plenty, as the crow flies
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.strike is None
    assert out.reason == "out_of_reach"
    assert out.reach.in_reach is False
    assert out.reach.shortfall_m == pytest.approx(5.0)   # 6m gap, 1m reach
    # Verified against movement_reach: running is same-elevation only, so the
    # actor does not move at all — landing == actor_pos.
    assert out.travelled_m == pytest.approx(0.0)


def test_a_legal_close_on_the_same_level_produces_a_strike():
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(2, 10, 0),
        target_pos=Position(6, 10, 0),      # 4m away on the ground
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert isinstance(out.strike, StrikePlan)
    assert out.strike.blind is False
    assert out.reason == ""
    assert out.reach.in_reach is True
    assert out.travelled_m == pytest.approx(3.0)   # stops 1m short: reach


def test_a_close_that_runs_out_of_movement_lands_short_and_does_not_strike():
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(2, 10, 0),
        target_pos=Position(18, 10, 0),     # 16m away
        mode="running",
        half_move_m=6.0,                    # not enough
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.strike is None
    assert out.reason == "out_of_reach"
    assert out.travelled_m == pytest.approx(6.0)     # spent the whole budget
    assert out.distance_after_m == pytest.approx(10.0)


def test_reach_is_judged_before_perception():
    # An attacker who never got close has no attack to gate. Reporting
    # "unperceived" for someone six metres below names the wrong failure.
    scene = _rooftop_arena()
    out = resolve_move_strike(
        scene=scene,
        actor_pos=Position(15, 10, 6),
        target_pos=Position(15, 10, 0),
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id="cheshire",
        target_invisible=True,              # also unperceivable
    )
    assert out.reason == "out_of_reach"


def test_a_sceneless_close_still_applies_the_reach_rule():
    # No scene ⇒ no legality to consult, so the close is a straight line. The
    # reach rule still decides whether the strike happens.
    out = resolve_move_strike(
        scene=None,
        actor_pos=Position(0, 0, 0),
        target_pos=Position(30, 0, 0),
        mode="running",
        half_move_m=6.0,
        reach_m=1.0,
        actor_id="cheshire",
    )
    assert out.strike is None
    assert out.reason == "out_of_reach"
    assert out.distance_after_m == pytest.approx(24.0)


def test_the_composite_is_on_the_import_surface():
    import kirby_combat

    assert kirby_combat.resolve_move_strike is resolve_move_strike
    assert kirby_combat.MoveStrikeOutcome is MoveStrikeOutcome
