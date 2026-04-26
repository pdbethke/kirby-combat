"""Autofire — power Advantage; weapon fires multiple shots per phase.

Per 6E2 p44 §AUTOFIRE:
    - Single target: ONE Attack Roll. If it hits, hits 1 + (margin / 2)
      times, capped at the autofire's "shots" stat (typically 5, 10, etc.).
    - Multiple targets: separate Attack Rolls per target, with a -1 OCV
      penalty per 2m of straight line between consecutive targets. Order
      is the attacker's choice.
    - DCV unchanged (autofire is a power feature, not a phase-spending stance).
    - Full-phase action.

The previous implementation applied a cumulative -2/shot OCV penalty
(Multiple Attack mechanics) to every shot — which is RAW for Multiple
Attack, but NOT for Autofire.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AutofireSingleTargetOutcome:
    """Result of a single-target Autofire attack."""
    hit: bool
    margin: int             # only meaningful if hit (negative if miss)
    hit_count: int          # 1 + (margin // 2), capped at autofire_shots
    autofire_shots: int     # the power's shots stat (5/10/etc.)


@dataclass(frozen=True)
class MultiTargetSpec:
    """Specification of a single target in a multi-target Autofire burst."""
    target_id: str
    target_dcv: int
    distance_to_prev_m: float = 0.0   # straight-line distance from previous target


@dataclass(frozen=True)
class MultiTargetHit:
    """Result of one Attack Roll in a multi-target Autofire burst."""
    target_id: str
    hit: bool
    margin: int
    effective_ocv: int
    line_penalty: int       # -1 OCV per 2m of line from previous target


def resolve_autofire_single_target(
    *,
    attacker_ocv: int,
    target_dcv: int,
    attacker_roll: int,
    autofire_shots: int,
) -> AutofireSingleTargetOutcome:
    """Resolve a single-target Autofire burst per 6E2 p44.

    One Attack Roll; on hit, deals 1 + (margin // 2) shots, capped at the
    power's shot count.

    Args:
        attacker_ocv: Attacker's effective OCV (including any modifiers).
        target_dcv: Target's effective DCV.
        attacker_roll: 3d6 sum.
        autofire_shots: Maximum shots the power can fire (5, 10, etc.).
    """
    if autofire_shots < 1:
        raise ValueError("autofire_shots must be >= 1")
    margin = (attacker_ocv + 11 - attacker_roll) - target_dcv
    if margin < 0:
        return AutofireSingleTargetOutcome(
            hit=False, margin=margin, hit_count=0,
            autofire_shots=autofire_shots,
        )
    hit_count = min(1 + (margin // 2), autofire_shots)
    return AutofireSingleTargetOutcome(
        hit=True, margin=margin, hit_count=hit_count,
        autofire_shots=autofire_shots,
    )


def resolve_autofire_multi_target(
    *,
    attacker_ocv: int,
    targets: list[MultiTargetSpec],
    attacker_rolls: list[int],
    autofire_shots: int,
) -> list[MultiTargetHit]:
    """Resolve a multi-target Autofire burst per 6E2 p44.

    Separate Attack Roll per target, with a -1 OCV penalty per 2m of
    straight line connecting consecutive targets. Targets are ordered as
    the attacker chose (caller's responsibility).

    Args:
        attacker_ocv: Attacker's base effective OCV (without line penalty).
        targets: Ordered list of targets with DCV and distance to predecessor.
        attacker_rolls: 3d6 sum per target (one per target, parallel order).
        autofire_shots: Maximum shots the power can fire — for caller info;
            does not cap hit counts here (one shot per target).
    """
    if len(targets) != len(attacker_rolls):
        raise ValueError("targets and attacker_rolls must have the same length")
    if len(targets) > autofire_shots:
        raise ValueError(
            f"cannot fire at {len(targets)} targets with only {autofire_shots} shots"
        )

    results: list[MultiTargetHit] = []
    cumulative_distance_m = 0.0
    for i, (spec, roll) in enumerate(zip(targets, attacker_rolls)):
        # First target: no line penalty. Subsequent targets accumulate the
        # line penalty per 6E2 p44 (-1 OCV per 2m of line from previous).
        if i == 0:
            line_penalty = 0
        else:
            cumulative_distance_m += max(0.0, spec.distance_to_prev_m)
            line_penalty = -(int(cumulative_distance_m) // 2)
        effective_ocv = attacker_ocv + line_penalty
        margin = (effective_ocv + 11 - roll) - spec.target_dcv
        results.append(
            MultiTargetHit(
                target_id=spec.target_id,
                hit=(margin >= 0),
                margin=margin,
                effective_ocv=effective_ocv,
                line_penalty=line_penalty,
            )
        )
    return results
