"""Area of Effect targeting computations for HERO System 6E.

Shapes: Radius, Cone, Line, Selective (post-filter).
Modifier: Explosion (DC falloff by distance from epicenter).

The basic shape methods are pure math (xy-positions only). Optional scene
integration kwargs (scene + indirect) layer wall-blocking and hazard-along-
path resolution on top, per Plan 1 Task 29.

Engine has zero runtime deps — only stdlib + this package.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from kirby_combat.scene.scene import Scene
    from kirby_combat.scene.hazards import HazardTriggerResult


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class AoEOutcome:
    affected_targets: list[str]           # combatant IDs hit
    per_target_dc: dict[str, int]         # DC each target takes
    target_dcv_for_aoe: int               # = 3 (HERO RAW: targets the hex)
    phase_cost: Literal["half", "full"]   # = "full" for all AoE shapes
    hazard_triggers: list = None          # type: list[HazardTriggerResult]; populated when a Scene is provided

    def __post_init__(self):
        if self.hazard_triggers is None:
            self.hazard_triggers = []


# ---------------------------------------------------------------------------
# Private geometry helpers
# ---------------------------------------------------------------------------

def _distance_2d(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Euclidean distance between two 2-D points."""
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return math.sqrt(dx * dx + dy * dy)


def _angle_between(origin: tuple[float, float], target: tuple[float, float]) -> float:
    """Angle in radians from origin to target, in [-π, π]."""
    dx = target[0] - origin[0]
    dy = target[1] - origin[1]
    return math.atan2(dy, dx)


def _angle_diff(a: float, b: float) -> float:
    """Smallest absolute angular difference between two angles, result in [0, π]."""
    diff = abs(a - b) % (2 * math.pi)
    if diff > math.pi:
        diff = 2 * math.pi - diff
    return diff


def _perpendicular_distance_to_segment(
    point: tuple[float, float],
    seg_start: tuple[float, float],
    seg_end: tuple[float, float],
) -> float:
    """Perpendicular distance from *point* to the line segment [seg_start, seg_end].

    The projection parameter t is clamped to [0, 1] so that points beyond the
    endpoints use the endpoint distance rather than the infinite-line distance.
    """
    sx, sy = seg_start
    ex, ey = seg_end
    px, py = point

    dx = ex - sx
    dy = ey - sy
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq == 0.0:
        # Degenerate segment — treat as a point
        return _distance_2d(point, seg_start)

    # Parameter t for the projection of point onto the infinite line
    t = ((px - sx) * dx + (py - sy) * dy) / seg_len_sq
    # Clamp to segment extent
    t = max(0.0, min(1.0, t))

    # Closest point on segment
    closest_x = sx + t * dx
    closest_y = sy + t * dy

    return _distance_2d(point, (closest_x, closest_y))


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

def _scene_filter_los(
    scene: "Scene",
    origin_xy: tuple[float, float],
    origin_z: float,
    affected: list[str],
    indirect: bool,
) -> list[str]:
    """Drop combatants whose LoS from the AoE origin is blocked.

    Per 6E1 p339, Indirect bypasses obstacles, so when indirect=True every
    affected target stays in the list.
    """
    from kirby_combat.scene.scene import Position
    from kirby_combat.scene.geometry import line_of_sight_clear

    if indirect:
        return list(affected)
    out: list[str] = []
    origin_pos = Position(x=origin_xy[0], y=origin_xy[1], z=origin_z)
    for cid in affected:
        target_pos = scene.combatant_positions.get(cid)
        if target_pos is None:
            out.append(cid)               # no positional data — keep
            continue
        if line_of_sight_clear(origin_pos, target_pos, scene.walls):
            out.append(cid)
    return out


def _hazards_along_path(
    scene: "Scene",
    origin_xy: tuple[float, float],
    end_xy: tuple[float, float],
    elevation_z: float,
) -> list:
    """Return HazardTriggerResults for hazards the path crosses (no combatants).

    Useful for AoE Line attacks: the projectile may strike a hazard mid-path
    even before reaching its end point. We synthesize a single virtual
    'aoe_path' combatant to use the existing crossing-detection code.
    """
    from kirby_combat.scene.scene import Position
    from kirby_combat.scene.hazards import compute_hazard_triggers

    before = {"_aoe_path_": Position(x=origin_xy[0], y=origin_xy[1], z=elevation_z)}
    after = {"_aoe_path_": Position(x=end_xy[0], y=end_xy[1], z=elevation_z)}
    return compute_hazard_triggers(
        scene=scene,
        combatant_positions_before=before,
        combatant_positions_after=after,
        phase="movement",
    )


class AreaOfEffect:
    name: str = "area_of_effect"

    @staticmethod
    def compute_radius(
        *,
        base_dc: int,
        epicenter: tuple[float, float],
        radius_m: float,
        combatant_positions: dict[str, tuple[float, float]],
        explosion: bool = False,
        scene: Optional["Scene"] = None,
        indirect: bool = False,
    ) -> AoEOutcome:
        """Compute a circular AoE.

        All combatants within *radius_m* of *epicenter* are affected.
        If *explosion* is True, per-target DC is reduced by 1 per 2 m from epicenter
        (minimum 0).
        """
        affected: list[str] = []
        per_target_dc: dict[str, int] = {}

        for cid, pos in combatant_positions.items():
            dist = _distance_2d(epicenter, pos)
            if dist <= radius_m:
                affected.append(cid)
                if explosion:
                    dc = max(0, base_dc - math.floor(dist / 2))
                else:
                    dc = base_dc
                per_target_dc[cid] = dc

        # Scene-aware filter: drop targets whose LoS from epicenter is blocked
        if scene is not None and not indirect:
            # Use mean z of all hit targets, or scene-floor if no targets
            origin_z = (
                sum(scene.combatant_positions[cid].z for cid in affected if cid in scene.combatant_positions)
                / max(1, len(affected)) if affected else scene.bounds.min_z
            )
            kept = set(_scene_filter_los(scene, epicenter, origin_z, affected, indirect=False))
            affected = [cid for cid in affected if cid in kept]
            per_target_dc = {cid: dc for cid, dc in per_target_dc.items() if cid in kept}

        return AoEOutcome(
            affected_targets=affected,
            per_target_dc=per_target_dc,
            target_dcv_for_aoe=3,
            phase_cost="full",
        )

    @staticmethod
    def compute_cone(
        *,
        base_dc: int,
        origin: tuple[float, float],
        direction_rad: float,
        half_angle_rad: float = math.pi / 6,  # 30° → 60° total cone
        length_m: float,
        combatant_positions: dict[str, tuple[float, float]],
        scene: Optional["Scene"] = None,
        indirect: bool = False,
        attacker_facing_rad: Optional[float] = None,
    ) -> AoEOutcome:
        """Compute a cone-shaped AoE.

        A combatant is hit if:
        1. Their distance from *origin* is ≤ *length_m*.
        2. The angle from *origin* to the combatant is within *half_angle_rad* of
           *direction_rad* (accounting for wraparound).
        """
        affected: list[str] = []
        per_target_dc: dict[str, int] = {}

        # If attacker_facing is given and direction_rad is the default, use facing.
        actual_direction = attacker_facing_rad if attacker_facing_rad is not None else direction_rad

        for cid, pos in combatant_positions.items():
            dist = _distance_2d(origin, pos)
            if dist > length_m:
                continue

            target_angle = _angle_between(origin, pos)
            diff = _angle_diff(target_angle, actual_direction)
            if diff <= half_angle_rad:
                affected.append(cid)
                per_target_dc[cid] = base_dc

        if scene is not None and not indirect:
            origin_z = scene.bounds.min_z
            for cid in affected:
                if cid in scene.combatant_positions:
                    origin_z = scene.combatant_positions[cid].z
                    break
            kept = set(_scene_filter_los(scene, origin, origin_z, affected, indirect=False))
            affected = [cid for cid in affected if cid in kept]
            per_target_dc = {cid: dc for cid, dc in per_target_dc.items() if cid in kept}

        return AoEOutcome(
            affected_targets=affected,
            per_target_dc=per_target_dc,
            target_dcv_for_aoe=3,
            phase_cost="full",
        )

    @staticmethod
    def compute_line(
        *,
        base_dc: int,
        start: tuple[float, float],
        end: tuple[float, float],
        width_m: float,
        combatant_positions: dict[str, tuple[float, float]],
        scene: Optional["Scene"] = None,
        indirect: bool = False,
        elevation_z: float = 0.0,
    ) -> AoEOutcome:
        """Compute a line-shaped AoE.

        A combatant is hit if their perpendicular distance to the line segment
        [*start*, *end*] is ≤ *width_m* / 2.  Points beyond the segment endpoints
        use the endpoint distance (clamped projection).
        """
        half_width = width_m / 2.0
        affected: list[str] = []
        per_target_dc: dict[str, int] = {}

        for cid, pos in combatant_positions.items():
            perp_dist = _perpendicular_distance_to_segment(pos, start, end)
            if perp_dist <= half_width:
                affected.append(cid)
                per_target_dc[cid] = base_dc

        hazard_triggers: list = []
        if scene is not None:
            if not indirect:
                kept = set(_scene_filter_los(scene, start, elevation_z, affected, indirect=False))
                affected = [cid for cid in affected if cid in kept]
                per_target_dc = {cid: dc for cid, dc in per_target_dc.items() if cid in kept}
            # Hazards crossed by the line projectile path
            hazard_triggers = _hazards_along_path(scene, start, end, elevation_z)

        return AoEOutcome(
            affected_targets=affected,
            per_target_dc=per_target_dc,
            target_dcv_for_aoe=3,
            phase_cost="full",
            hazard_triggers=hazard_triggers,
        )

    @staticmethod
    def selective_filter(
        outcome: AoEOutcome,
        *,
        excluded_ids: set[str],
    ) -> AoEOutcome:
        """Return a new AoEOutcome with *excluded_ids* removed.

        Uses dataclasses.replace so the original outcome is not mutated.
        """
        new_affected = [t for t in outcome.affected_targets if t not in excluded_ids]
        new_per_dc = {k: v for k, v in outcome.per_target_dc.items() if k not in excluded_ids}
        return replace(
            outcome,
            affected_targets=new_affected,
            per_target_dc=new_per_dc,
        )
