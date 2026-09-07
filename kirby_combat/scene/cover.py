"""Cover resolution.

Two layers:
  1. ``compute_cover_level`` — scene-aware analysis returning a 0-4 abstract
     cover *level* (a property of Walls/Surfaces, not directly the OCV penalty).
  2. ``cover_ocv_modifier(percent_covered)`` — RAW lookup: percent of target
     covered → OCV penalty per 6E2 p45 §BEHIND COVER MODIFIERS.

Per 6E2 p45 §BEHIND COVER MODIFIERS, the OCV penalty has six discrete buckets:
    0-10%   →  0    (no cover / under cover but exposed)
    11-24%  → -1    (light cover, e.g., behind a chair)
    25-50%  → -2    (half cover, e.g., behind a low wall, knee-deep in water)
    51-74%  → -3    (heavy cover, e.g., crouched behind a wall)
    75-90%  → -4    (full cover except head/torso)
    91-100% → -8    (head only / full cover)

Algorithm for ``compute_cover_level`` (scene analysis):
    1. If LoS clear (no walls intersect between shooter and target with sufficient
       height to block), no wall cover applies from sight-blocking walls.
    1b. A LOW wall standing in the line still gives its cover_level, even
       though it does not block sight — the table above names exactly this
       ("behind a low wall"). Taken only when no blocking wall gives more.
    2. Otherwise, of the walls that block LoS, pick the one whose midpoint is
       closest to the target — that's the wall providing cover.
    3. Surface cover: if target's (x, y) is inside a surface polygon and that
       surface has cover_level > 0, take max(wall_cover, surface_cover).
    4. If target_is_prone_or_diving, add +1 (capped at 4) — but ONLY if the
       base cover is already > 0 (RAW: prone alone in open ground = no cover).
"""
from __future__ import annotations

from kirby_combat.scene.scene import Position, Scene, Wall, Surface
from kirby_combat.scene.geometry import (
    distance_3d, first_blocking_wall, point_in_polygon_xy,
    segments_intersect_xy,
)


# Per 6E2 p45 §BEHIND COVER MODIFIERS — discrete percent-of-target-covered
# buckets map to OCV penalties. Each tuple is (max_percent_in_bucket, ocv_mod).
_COVER_PERCENT_TO_OCV: list[tuple[int, int]] = [
    (10, 0),      # 0-10%: no penalty
    (24, -1),     # 11-24%: light cover
    (50, -2),     # 25-50%: half cover
    (74, -3),     # 51-74%: heavy cover
    (90, -4),     # 75-90%: full cover except head/torso
    (100, -8),    # 91-100%: head only / full cover
]


def cover_ocv_modifier(percent_covered: int) -> int:
    """Return the OCV penalty for an attack on a target this percent covered.

    Per 6E2 p45 §BEHIND COVER MODIFIERS. Input is clamped to [0, 100].
    """
    pct = max(0, min(100, int(percent_covered)))
    for max_pct, mod in _COVER_PERCENT_TO_OCV:
        if pct <= max_pct:
            return mod
    return -8  # safety fallback (unreachable after clamp)


def _wall_blocks_los(shooter: Position, target: Position, wall: Wall) -> bool:
    """True if this single wall blocks the LoS between shooter and target.

    Delegates to geometry.first_blocking_wall — the single shared height-aware
    predicate — rather than hand-copying its logic, so this can never diverge
    from it again (see supported-vantages whole-branch review: a prior
    hand-copy used `<=` where first_blocking_wall uses strict `<`, which was
    unreachable before wall tops became standable and inverted cover for
    anyone standing exactly on a wall top once they did).
    """
    if not wall.blocks_los:
        return False
    return first_blocking_wall(shooter, target, [wall]) is not None


def _low_wall_between(shooter: Position, target: Position, wall: Wall) -> bool:
    """Does a wall too LOW to block sight still stand between these two?

    THE MODULE'S OWN TABLE NAMES THIS CASE and it was not implemented:
    "25-50% -> -2 (half cover, e.g., BEHIND A LOW WALL, knee-deep in
    water)". `_wall_blocks_los` returns False for any wall with
    ``blocks_los=False``, and those are precisely the low walls -- so a
    parapet you can see and shoot over gave ZERO cover, which is the
    opposite of what a parapet is for.

    It matters beyond one rule. The arena generator makes roughly 40% of
    its walls low cover ON PURPOSE, after an all-blocking arena sent the AI
    breaching instead of fighting -- and every one of those was cosmetic.

    The test is 2D and deliberately so: a wall that does not block sight
    still stands in the line, and how much of the target it hides is what
    its ``cover_level`` already says.
    """
    if wall.blocks_los:
        return False        # handled by the height-aware predicate
    a, b = wall.segment
    return segments_intersect_xy(
        (shooter.x, shooter.y), (target.x, target.y), (a.x, a.y), (b.x, b.y),
    )


def _wall_midpoint(wall: Wall) -> Position:
    a, b = wall.segment
    return Position(
        x=(a.x + b.x) / 2.0,
        y=(a.y + b.y) / 2.0,
        z=(a.z + b.z) / 2.0,
    )


def _surface_cover_for(target: Position, surfaces: list[Surface]) -> int:
    """Return the max cover_level of any surface containing the target's xy.

    Surfaces matter for cover only when they have cover_level > 0
    (foxholes, rubble, etc.). Standard ground surfaces have cover_level=0.
    """
    best = 0
    for surf in surfaces:
        if surf.cover_level <= 0:
            continue
        if point_in_polygon_xy((target.x, target.y), surf.polygon_xy):
            best = max(best, surf.cover_level)
    return best


def compute_cover_level(
    *,
    shooter_pos: Position,
    target_pos: Position,
    target_is_prone_or_diving: bool,
    scene: Scene,
) -> int:
    """Return cover level 0-4 the target enjoys against the shooter.

    Caller converts to OCV penalty per the 6E table.
    """
    # 1. Find blocking walls; pick the one nearest the target.
    blocking = [w for w in scene.walls if _wall_blocks_los(shooter_pos, target_pos, w)]
    wall_cover = 0
    if blocking:
        nearest = min(blocking, key=lambda w: distance_3d(_wall_midpoint(w), target_pos))
        wall_cover = nearest.cover_level

    # 1b. LOW walls. They do not block sight, and they are still cover --
    # this module's own table gives "behind a low wall" as the -2 example.
    # Taken only when no sight-blocking wall already gives more, so a
    # parapet never downgrades a building.
    low = [w for w in scene.walls if _low_wall_between(shooter_pos, target_pos, w)]
    if low:
        nearest_low = min(
            low, key=lambda w: distance_3d(_wall_midpoint(w), target_pos),
        )
        wall_cover = max(wall_cover, nearest_low.cover_level)

    # 2. Surface cover (foxhole etc).
    surface_cover = _surface_cover_for(target_pos, scene.surfaces)

    base_cover = max(wall_cover, surface_cover)

    # 3. Prone / diving bonus — only when there's existing cover.
    if target_is_prone_or_diving and base_cover > 0:
        return min(4, base_cover + 1)
    return base_cover


#: How far from a feature to stand when taking cover behind it, in metres.
#: Close enough that the feature covers you, far enough not to be inside it.
COVER_STANDOFF_M = 1.0


def cover_spot(wall: Wall, threat: Position, standoff_m: float = COVER_STANDOFF_M) -> Position:
    """Where to stand to put ``wall`` between you and ``threat``.

    ADJACENT TO THE FEATURE, ON ITS FAR SIDE FROM THE THREAT --- which is
    how a tactics game models cover and how cover actually works. You do
    not move *behind* an obstacle in the sense of crossing it; you move
    against it, and it shields you from whoever is beyond.

    The spot is the wall's midpoint pushed one standoff along the
    perpendicular to its own line, in whichever direction is further from
    the threat.
    """
    import math

    a, b = wall.segment
    mx, my, mz = (a.x + b.x) / 2.0, (a.y + b.y) / 2.0, (a.z + b.z) / 2.0
    dx, dy = b.x - a.x, b.y - a.y
    length = math.hypot(dx, dy) or 1.0
    px, py = -dy / length, dx / length

    plus = (mx + px * standoff_m, my + py * standoff_m)
    minus = (mx - px * standoff_m, my - py * standoff_m)
    if math.dist(plus, (threat.x, threat.y)) >= math.dist(minus, (threat.x, threat.y)):
        return Position(plus[0], plus[1], mz)
    return Position(minus[0], minus[1], mz)


def cover_available(
    wall: Wall, from_pos: Position, threats: list[Position], scene: Scene,
) -> tuple[Position, int]:
    """The spot behind ``wall`` and the cover it would ACTUALLY give.

    WHY THIS IS COMPUTED RATHER THAN ASSUMED. A feature only shields you
    from threats on its far side. Offering "take cover behind the crates"
    for a wall that sits BEHIND you gives a chooser an option that cannot
    help, and this engine did exactly that until it was measured: the
    actor moved, stopped against the wall it could not cross, and finished
    the Phase with the same cover it started with.

    The level returned is the BEST cover the spot gives against any single
    threat. This was the WORST until 2026-09-07, on the reasoning that
    "cover that only works against one of three shooters is not cover you
    can rely on" --- which reads well and is wrong twice.

    It is wrong about the RULES. Resolution applies cover PER
    shooter-target pair (`_cover_against` in actions/recording.py), so a
    barrel genuinely costs the man in front of it -2 OCV and costs the man
    who flanked it nothing. Scoring the barrel 0 described a game the
    engine does not play.

    And it is wrong about the FIGHT that exposed it. Nine men in a lot
    5.5m across means every feature is flanked by somebody, so every one
    scored 0 and no cover was ever offered --- on a map furnished with
    barrels, a trough and packing crates precisely so that it would be.

    `cover_breakdown` gives the other half, how MANY threats the spot
    covers, so an offer can state the trade instead of one number that
    hides it.

    Returns ``(spot, 0)`` only when the feature shields the actor from
    NOBODY --- a wall behind you --- and the caller declines to offer it.
    """
    if not threats:
        return from_pos, 0
    nearest = min(threats, key=lambda t: distance_3d(from_pos, t))
    spot = cover_spot(wall, nearest)
    best = max(
        compute_cover_level(
            shooter_pos=threat, target_pos=spot,
            target_is_prone_or_diving=False, scene=scene,
        )
        for threat in threats
    )
    return spot, best


def cover_breakdown(
    wall: Wall, spot: Position, threats: list[Position], scene: Scene,
) -> tuple[int, int]:
    """How many of ``threats`` the ``spot`` actually covers, and how many
    there are --- the flanking picture, as two numbers.

    Separate from `cover_available` because they answer different
    questions: how GOOD the cover is, and how much of the problem it
    solves. An offer that quotes only the first invites a fighter to hide
    from one man while four others walk around it.
    """
    covered = sum(
        1 for threat in threats
        if compute_cover_level(
            shooter_pos=threat, target_pos=spot,
            target_is_prone_or_diving=False, scene=scene,
        ) > 0
    )
    return covered, len(threats)
