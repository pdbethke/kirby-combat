"""Close and strike — the half-move-then-attack composite, and the reach gate.

This is the worked example the import-surface ratchet owed for the reach rule
(6E2 p36, 6E2 p56): hand-to-hand combat needs the target inside the
attacker's Reach, measured where the attacker actually ENDS UP.

The fight that motivated it: an attacker on a rooftop declared a martial throw
on an enemy standing on the street six metres below. Running is a
same-elevation mode, so the close legally went nowhere -- and before this
composite existed, the throw resolved anyway across the six-metre drop.

This is a demo script, not a test. Run with:
    .venv/bin/python examples/close_and_strike.py
"""
from __future__ import annotations

from kirby_combat import resolve_move_strike, within_reach
from kirby_combat.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)


def _urban_block() -> Scene:
    """A street at ground level, with a six-metre rooftop over half of it."""
    return Scene(
        id="urban-block", name="Urban Block",
        bounds=SceneBounds(0, 0, 0, 20, 20, 20),
        surfaces=[
            Surface(id="street", name="Street",
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


def _report(label: str, out) -> None:
    print(f"\n{label}")
    print(f"  moved      : {out.travelled_m:.1f}m")
    print(f"  gap after  : {out.distance_after_m:.1f}m (reach {out.reach.reach_m:.1f}m)")
    if out.strike is None:
        print(f"  NO STRIKE  : {out.reason}, short by {out.reach.shortfall_m:.1f}m")
    else:
        print(f"  STRIKE     : blind={out.strike.blind}")


def main() -> None:
    scene = _urban_block()
    reach = 1.0   # an unaugmented human's Reach, 6E2 p56

    print("=" * 68)
    print("Close and strike (6E2 p36, 6E2 p56)")
    print("=" * 68)

    # The rule on its own: a bare distance, judged against a bare Reach.
    print("\nThe rule, applied to two distances:")
    for gap in (0.8, 6.0):
        v = within_reach(gap, reach)
        print(f"  {gap:.1f}m vs {reach:.1f}m reach -> in_reach={v.in_reach}, "
              f"shortfall {v.shortfall_m:.1f}m")

    # 1. The defect. Rooftop attacker, street-level target, running close.
    _report(
        "1. Rooftop -> street, running (the bug this composite closes):",
        resolve_move_strike(
            scene=scene,
            actor_pos=Position(15, 10, 6),
            target_pos=Position(15, 10, 0),
            mode="running", half_move_m=6.0, reach_m=reach,
            actor_id="attacker",
        ),
    )

    # 2. The same close on flat ground, where it is legal.
    _report(
        "2. Street -> street, 4m apart, running:",
        resolve_move_strike(
            scene=scene,
            actor_pos=Position(2, 10, 0),
            target_pos=Position(6, 10, 0),
            mode="running", half_move_m=6.0, reach_m=reach,
            actor_id="attacker",
        ),
    )

    # 3. Legal direction, not enough movement: lands short, no strike.
    _report(
        "3. Street -> street, 16m apart on a 6m half move:",
        resolve_move_strike(
            scene=scene,
            actor_pos=Position(2, 10, 0),
            target_pos=Position(18, 10, 0),
            mode="running", half_move_m=6.0, reach_m=reach,
            actor_id="attacker",
        ),
    )

    # 4. Flight is free in three dimensions, so the rooftop gap closes.
    _report(
        "4. Rooftop -> street, flight:",
        resolve_move_strike(
            scene=scene,
            actor_pos=Position(15, 10, 6),
            target_pos=Position(15, 10, 0),
            mode="flight", half_move_m=6.0, reach_m=reach,
            actor_id="attacker",
        ),
    )

    print("\nThe gate is measured at the LANDING position, never at the "
          "position\nthe action was declared from.")


if __name__ == "__main__":
    main()
