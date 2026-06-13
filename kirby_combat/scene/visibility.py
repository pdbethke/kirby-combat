"""Analytic visibility geometry for LoS-aware repositioning (spec
2026-06-13-los-aware-repositioning-design §1). Pure: given an observer, a
target, and the scene's occluders, find the nearest point with a clear line
of fire (offensive) or that breaks the threat's line (defensive). Candidates
are derived analytically from occluder shadow geometry, then VERIFIED with the
real LoS test — exact, not sampled."""
from __future__ import annotations

from kirby_combat.scene.scene import Position, Scene, Wall
from kirby_combat.scene.geometry import first_blocking_wall, line_of_sight_clear

_EPS = 0.5  # metres past a shadow edge / above a wall top


def _dist(a: Position, b: Position) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5


def _wall_top(w: Wall) -> float:
    return max(w.segment[0].z, w.segment[1].z) + w.height_m


def _shadow_candidates(observer: Position, target: Position, wall: Wall,
                       vertical_reach: float) -> list[Position]:
    """Analytic candidate destinations that should clear `wall`'s shadow:
    over-the-top (vertical) + just past each wall END (flank).

    The candidate set is tunable — the load-bearing correctness gate is the
    `line_of_sight_clear` verification in `nearest_visible_point`. We emit a
    spread of lateral offsets past each endpoint (and over the top, when
    vertical reach allows) so the nearest LoS-clear candidate is found."""
    out: list[Position] = []
    # (a) over-the-top — rise straight up above the wall, if reach allows.
    top = _wall_top(wall) + _EPS
    if observer.z + vertical_reach >= top:
        out.append(Position(observer.x, observer.y, top))
    # (b) flank each end — step PAST the endpoint, away from the target,
    #     at the observer's z (go around the end on the ground). Emit a range
    #     of step multiples so a longer flank is available when a short one
    #     still grazes the wall.
    for end in (wall.segment[0], wall.segment[1]):
        dx, dy = end.x - target.x, end.y - target.y
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / n, dy / n
        for steps in (1.0, 2.0, 4.0, 8.0, 16.0):
            out.append(Position(end.x + steps * _EPS * ux,
                                end.y + steps * _EPS * uy, observer.z))
    return out


def nearest_visible_point(observer: Position, target: Position, scene: Scene, *,
                          radius: float, vertical_reach: float = 0.0
                          ) -> Position | None:
    """Closest point to `observer`, within `radius`, with a clear line of fire
    to `target`. Returns `observer` when already clear; None when no analytic
    candidate within radius has LoS. (The caller validates reachability + a
    supported landing per movement mode via movement_reach.)"""
    walls = [w for w in scene.walls if getattr(w, "blocks_los", True)]
    if line_of_sight_clear(observer, target, walls):
        return observer
    wall = first_blocking_wall(observer, target, walls)
    if wall is None:
        return None
    best: Position | None = None
    best_d = float("inf")
    for c in _shadow_candidates(observer, target, wall, vertical_reach):
        d = _dist(observer, c)
        if d > radius:
            continue
        if not line_of_sight_clear(c, target, walls):  # VERIFY vs ALL walls
            continue
        if d < best_d:
            best, best_d = c, d
    return best


def _radial_away_candidates(observer: Position, threat: Position,
                            radius: float) -> list[Position]:
    """Open-range fallback candidates: points on the ground spread around the
    observer, biased away from the threat. Emitted at several fractions of the
    radius across 8 compass directions so the farthest-from-threat reachable
    point can be picked."""
    import math
    out: list[Position] = []
    for i in range(8):
        ang = i * math.pi / 4.0
        ux, uy = math.cos(ang), math.sin(ang)
        for frac in (1.0, 0.75, 0.5):
            r = radius * frac
            out.append(Position(observer.x + r * ux,
                                observer.y + r * uy, observer.z))
    return out


def nearest_hidden_point(observer: Position, threat: Position, scene: Scene, *,
                         radius: float, vertical_reach: float = 0.0
                         ) -> Position | None:
    """Break contact: the nearest point, within `radius`, that the `threat`
    cannot see (behind cover) — else, if no cover is reachable, the point that
    opens the most range (farthest from the threat within `radius`).

    Decision rule (prefer-cover-then-open-range):

      1. If the observer is **already hidden** from the threat (no clear line
         of sight threat->observer), no move is needed — return `observer`.
      2. Otherwise gather candidates: the shadow geometry of the nearest wall
         on the threat->observer line (points INTO a wall's shadow / behind
         cover) plus radial-away points (8 compass directions x fractions of
         the radius, biased away from the threat).
      3. Among reachable candidates (within `radius`), prefer the **nearest**
         one the threat cannot see (`line_of_sight_clear(threat, c, walls)` is
         False) — behind cover beats open range, and the closest such cover
         minimises exposure-time getting there.
      4. If no candidate breaks LoS (no reachable cover), return the candidate
         that **maximises distance from the threat** within `radius` — open
         range, the best available when cover isn't an option.

    Pure geometry: candidates are analytic, the cover test is the exact
    `line_of_sight_clear`. The caller validates reachability + a supported
    landing per movement mode (movement_reach)."""
    walls = [w for w in scene.walls if getattr(w, "blocks_los", True)]
    # (1) already hidden -> stay put.
    if not line_of_sight_clear(threat, observer, walls):
        return observer

    # (2) candidates: wall-shadow (behind cover) + radial-away (open range).
    candidates: list[Position] = []
    wall = first_blocking_wall(observer, threat, walls)
    if wall is None and walls:
        # No wall directly on the line, but cover may exist off to a flank:
        # consider every blocking wall's shadow geometry.
        for w in walls:
            candidates.extend(
                _shadow_candidates(observer, threat, w, vertical_reach))
    elif wall is not None:
        candidates.extend(
            _shadow_candidates(observer, threat, wall, vertical_reach))
    candidates.extend(_radial_away_candidates(observer, threat, radius))

    best_cover: Position | None = None
    best_cover_d = float("inf")
    best_open: Position | None = None
    best_open_far = -1.0
    for c in candidates:
        if _dist(observer, c) > radius:
            continue
        if not line_of_sight_clear(threat, c, walls):
            # (3) behind cover — prefer the nearest such point.
            d = _dist(observer, c)
            if d < best_cover_d:
                best_cover, best_cover_d = c, d
        else:
            # (4) open range — track the farthest-from-threat point.
            far = _dist(c, threat)
            if far > best_open_far:
                best_open, best_open_far = c, far
    if best_cover is not None:
        return best_cover
    return best_open
