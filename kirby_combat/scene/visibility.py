"""Analytic visibility geometry for LoS-aware repositioning (spec
2026-06-13-los-aware-repositioning-design §1). Pure: given an observer, a
target, and the scene's occluders, find the nearest point with a clear line
of fire (offensive) or that breaks the threat's line (defensive). Candidates
are derived analytically from occluder shadow geometry, then VERIFIED with the
real LoS test — exact, not sampled."""
from __future__ import annotations

from kirby_combat.scene.scene import Position, Scene, Surface, Wall
from kirby_combat.scene.geometry import first_blocking_wall, line_of_sight_clear
from kirby_combat.scene.falling import is_supported_at

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


def _nearest_point_on_segment(px: float, py: float, ax: float, ay: float,
                              bx: float, by: float) -> tuple[float, float]:
    """Closest point to (px, py) on the segment ab, in xy."""
    dx, dy = bx - ax, by - ay
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return (ax, ay)
    t = ((px - ax) * dx + (py - ay) * dy) / len_sq
    t = max(0.0, min(1.0, t))
    return (ax + t * dx, ay + t * dy)


def _surface_points(observer: Position,
                    surf: Surface) -> list[tuple[float, float]]:
    """Candidate xy points on `surf`: the point nearest the observer, the
    centroid, and every vertex.

    The vertices carry this feature. A surface's nearest point is very
    often still inside the blocking wall's shadow while one of its corners
    is outside it — in URBAN_ROOFTOP the ONLY vantage a teleporter can
    reach on a half-move is the rooftop's south-east vertex, and the
    nearest rooftop point to him is where he already stands.
    """
    poly = surf.polygon_xy
    if not poly:
        return []
    out: list[tuple[float, float]] = list(poly)
    out.append((sum(p[0] for p in poly) / len(poly),
                sum(p[1] for p in poly) / len(poly)))
    best, best_d2 = None, float("inf")
    for i in range(len(poly)):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % len(poly)]
        q = _nearest_point_on_segment(observer.x, observer.y, ax, ay, bx, by)
        d2 = (q[0] - observer.x) ** 2 + (q[1] - observer.y) ** 2
        if d2 < best_d2:
            best, best_d2 = q, d2
    if best is not None:
        out.append(best)
    return out


def _surface_candidates(observer: Position, scene: Scene,
                        vertical_reach: float,
                        radius: float) -> list[Position]:
    """Reachable points on the scene's supporting surfaces — authored
    surfaces and derived wall tops alike.

    This is the candidate family that makes "blink onto the roof edge"
    exist at all: `_shadow_candidates` emits only mid-air points, which
    every non-hovering mode is rejected from. A surface higher than
    `observer.z + vertical_reach` cannot be reached. A drop is always
    within reach EXCEPT for a mode with `vertical_reach == 0.0` (running,
    swimming) — those cannot change elevation at all, so a lower surface
    is just as unreachable as a higher one. (Leaping's descent is
    deliberately NOT capped by its rise limit — that asymmetry lives in
    movement_legality._leaping, which caps `rise` only — so this stays a
    one-sided gate, not `abs(delta) <= vertical_reach`.)
    """
    out: list[Position] = []
    for surf in scene.supporting_surfaces():
        if not surf.is_supporting:
            continue
        delta = surf.elevation_m - observer.z
        if delta > vertical_reach + _EPS:
            continue        # cannot climb that high
        if delta < -_EPS and vertical_reach <= _EPS:
            continue        # cannot change elevation at all, so cannot drop either
        for x, y in _surface_points(observer, surf):
            cand = Position(x, y, surf.elevation_m)
            if _dist(observer, cand) > radius:
                continue
            out.append(cand)
    return out


def nearest_visible_point(observer: Position, target: Position, scene: Scene, *,
                          radius: float, vertical_reach: float = 0.0,
                          require_support: bool = False,
                          ) -> Position | None:
    """Closest point to `observer`, within `radius`, with a clear line of fire
    to `target`. Returns `observer` when already clear; None when no analytic
    candidate within radius has LoS.

    `require_support=True` drops candidates with nothing underneath them, so
    a mode that cannot hover (see `movement_legality.mode_requires_support`)
    is never offered a destination it would be rejected from. (The caller
    still validates reachability per movement mode via movement_reach.)
    """
    walls = [w for w in scene.walls if getattr(w, "blocks_los", True)]
    if line_of_sight_clear(observer, target, walls):
        return observer
    wall = first_blocking_wall(observer, target, walls)
    if wall is None:
        return None
    candidates = _shadow_candidates(observer, target, wall, vertical_reach)
    candidates += _surface_candidates(observer, scene, vertical_reach, radius)
    best: Position | None = None
    best_d = float("inf")
    for c in candidates:
        d = _dist(observer, c)
        if d > radius:
            continue
        if require_support and not is_supported_at(c, scene):
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
                         radius: float, vertical_reach: float = 0.0,
                         require_support: bool = False,
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

    `require_support=True` drops candidates with nothing underneath them,
    so a mode that cannot hover is never offered a destination it would be
    rejected from.

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
    candidates.extend(
        _surface_candidates(observer, scene, vertical_reach, radius))

    best_cover: Position | None = None
    best_cover_d = float("inf")
    best_open: Position | None = None
    best_open_far = -1.0
    for c in candidates:
        if _dist(observer, c) > radius:
            continue
        if require_support and not is_supported_at(c, scene):
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
