"""Flank candidates must sit strictly outside a wall's shadow, not on its
boundary (supported-vantages plan, Task 12).

The original generator placed every flank candidate on the ray from the
target through a wall ENDPOINT, so the sightline back to the target grazed
that corner and `segments_intersect_xy`'s strict-CCW test resolved it on
floating-point rounding rather than geometry."""
from kirby_combat.scene.scene import Position, Wall
from kirby_combat.scene.geometry import line_of_sight_clear
from kirby_combat.scene.visibility import _shadow_candidates

WALL = Wall(
    id="stone", name="stone_wall",
    segment=(Position(-16.0, -5.0, 0.0), Position(-2.0, -5.0, 0.0)),
    height_m=8.0,
)
OBSERVER = Position(-10.0, -15.0, 0.0)
TARGET = Position(0.0, 13.0, 6.0)


def test_flank_candidates_are_monotonic_not_coin_flips():
    """Stepping further around a corner must not flip the sightline back
    and forth. Once a flank candidate clears the wall, every candidate
    further along that same flank must also clear it."""
    cands = _shadow_candidates(OBSERVER, TARGET, WALL, vertical_reach=0.0)
    flanks = [c for c in cands if abs(c.z - OBSERVER.z) < 1e-9]
    assert flanks, "the generator must still emit ground-level flanks"

    verdicts = [line_of_sight_clear(c, TARGET, [WALL]) for c in flanks]
    assert any(verdicts), "at least one flank must actually clear the wall"

    # Group by which wall end each candidate flanks, then require that once
    # a flank clears, it stays clear as it steps further out.
    for end in WALL.segment:
        same_side = [
            (c, v) for c, v in zip(flanks, verdicts)
            if (c.x - end.x) * (TARGET.x - end.x) <= 0
            or abs(c.x - end.x) < 12.0
        ]
        seen_clear = False
        for _c, v in same_side:
            if v:
                seen_clear = True
            elif seen_clear:
                # A blocked candidate AFTER a clear one on the same flank is
                # the coin-flip signature.
                assert False, (
                    f"blocked candidate {_c} appears after a clear one on "
                    f"the same flank (end={end}) — coin flip, not geometry"
                )


def test_no_flank_candidate_lies_exactly_on_a_shadow_boundary():
    """The load-bearing assertion. A candidate collinear with the target and
    a wall endpoint has a sightline that grazes the corner; whether that
    counts as blocked is then decided by rounding, not geometry."""
    cands = _shadow_candidates(OBSERVER, TARGET, WALL, vertical_reach=0.0)
    for c in cands:
        if abs(c.z - OBSERVER.z) > 1e-9:
            continue        # the over-the-top candidate, not a flank
        for end in WALL.segment:
            # cross product of (end - target) and (c - target); ~0 means the
            # three points are collinear.
            cross = ((end.x - TARGET.x) * (c.y - TARGET.y)
                     - (end.y - TARGET.y) * (c.x - TARGET.x))
            assert abs(cross) > 1e-6, (
                f"flank candidate {c} is collinear with the target and wall "
                f"endpoint ({end.x}, {end.y}) — its sightline grazes the "
                f"corner and its LoS verdict is a coin flip"
            )


def test_a_clear_flank_is_actually_found():
    """End-to-end: at least one emitted flank genuinely clears the wall,
    and does so robustly rather than by rounding."""
    cands = _shadow_candidates(OBSERVER, TARGET, WALL, vertical_reach=0.0)
    clear = [c for c in cands if line_of_sight_clear(c, TARGET, [WALL])]
    assert clear, "the flank generator must find at least one clear vantage"
