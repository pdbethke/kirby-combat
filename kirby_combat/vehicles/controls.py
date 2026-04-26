"""Vehicle controls — driving rolls and maneuvers.

Per 6E2 Skills: Combat Driving (or relevant Transport Familiarity) governs
vehicle handling. Failed driving rolls cause loss of control.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from kirby_combat.vehicles.vehicle import Vehicle


class Maneuver(Enum):
    STRAIGHT = "straight"            # no roll required
    SHARP_TURN = "sharp_turn"        # -2 base
    SWERVE = "swerve"                # -1 base, can abort to avoid collision
    BOOTLEG_TURN = "bootleg_turn"    # -3 base
    BARREL_ROLL = "barrel_roll"      # -5 base, vehicle-only


@dataclass
class DrivingRollResult:
    base_skill: int                  # combat_driving target number
    terrain_modifier: int
    velocity_modifier: int
    maneuver_modifier: int
    target_number: int
    roll: int
    success: bool
    loss_of_control: bool
    audit: list[str] = field(default_factory=list)


_MANEUVER_MOD: dict[Maneuver, int] = {
    Maneuver.STRAIGHT: 0,
    Maneuver.SHARP_TURN: -2,
    Maneuver.SWERVE: -1,
    Maneuver.BOOTLEG_TURN: -3,
    Maneuver.BARREL_ROLL: -5,
}


def driving_roll(
    base_skill: int,
    dice: list[int],
    maneuver: Maneuver = Maneuver.STRAIGHT,
    bumpy_terrain: bool = False,
    velocity_m_per_segment: float = 0.0,
) -> DrivingRollResult:
    """Resolve a single driving roll.

    base_skill is the character's Combat Driving (or Transport Familiarity)
    target number, e.g., 11 for an 11- skill. The roll succeeds on 3d6 <= TN.
    """
    if len(dice) != 3:
        raise ValueError(f"driving roll needs 3d6, got {len(dice)}")
    audit: list[str] = []
    terrain_mod = -2 if bumpy_terrain else 0
    # Above 30 m/segment: -1 per 30 over
    velocity_mod = -(int(velocity_m_per_segment) // 30) if velocity_m_per_segment > 30 else 0
    maneuver_mod = _MANEUVER_MOD[maneuver]
    target_number = base_skill + terrain_mod + velocity_mod + maneuver_mod
    roll = sum(dice)
    success = roll <= target_number
    audit.append(
        f"Driving roll: base={base_skill}, terrain={terrain_mod}, "
        f"velocity={velocity_mod}, maneuver={maneuver.value}({maneuver_mod}) "
        f"-> TN={target_number}, roll={roll} -> {'SUCCESS' if success else 'FAIL'}"
    )
    loss_of_control = not success
    return DrivingRollResult(
        base_skill=base_skill, terrain_modifier=terrain_mod,
        velocity_modifier=velocity_mod, maneuver_modifier=maneuver_mod,
        target_number=target_number, roll=roll, success=success,
        loss_of_control=loss_of_control, audit=audit,
    )


@dataclass
class SwerveResult:
    succeeded: bool
    avoided_collision: bool


def swerve_to_avoid(driving_roll_result: DrivingRollResult) -> SwerveResult:
    """A successful swerve avoids the impending collision."""
    return SwerveResult(
        succeeded=driving_roll_result.success,
        avoided_collision=driving_roll_result.success,
    )
