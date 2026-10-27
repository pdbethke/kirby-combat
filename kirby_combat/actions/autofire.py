"""Autofire --- the arithmetic of a burst (6E1 p.329; 6E2 p.44-45).

Pure numbers; the burst itself is resolved in `actions/autofire_attack.py`.

6E2 p.44, single target: "the character decides how many times he wants to
fire the attack, up to a maximum of the number of 'shots' he has purchased
... He makes a normal Attack Roll. If the Attack Roll succeeds, the character
hits the target one time; in addition, for every full 2 points by which the
Attack Roll succeeds, he hits the target an additional time ... A single
target cannot be hit more times than the number of 'shots' fired."

6E2 p.44, multiple targets: "a character declares the targets and counts the
line of meters 'connecting' all the targets. He suffers a -1 OCV penalty for
each 2m in the line. He must make a separate Attack Roll for each target
fired at, and each target can only get hit one time. He must fire a minimum
of one shot into each 2m 'area' of the line, even if no target occupies it
... If the character misses one of the targets, he may continue down the
line attempting to hit other targets."

CORRECTED: the multi-target helper charged each target only the line up to
it (-0 for the first, then a running total). The page charges the whole line
on every roll: the penalty is for the line he sweeps, not for how far along
it a man stands.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def burst_hits(margin: int, shots: int) -> int:
    """How many of ``shots`` hit one target, from the one roll's margin
    (6E2 p.44): one for making it, one more per full 2 points over."""
    if shots < 1:
        raise ValueError("autofire_shots must be >= 1")
    if margin < 0:
        return 0
    return min(1 + margin // 2, shots)


def line_penalty(line_m: float) -> int:
    """6E2 p.44: "-1 OCV penalty for each 2m in the line" (a negative OCV
    modifier; a part of 2m is not a 2m)."""
    return -(int(max(0.0, line_m)) // 2)


def shots_for_line(targets: int, line_m: float) -> int:
    """Shots a multi-target burst must fire: one into each 2m 'area' of the
    line, "even if no target occupies it", and never fewer than one per
    target. RULING, labelled: a part of a 2m area at the end of the line is
    an area (a shot must reach it, or the last man is not in the line)."""
    return max(int(targets), math.ceil(max(0.0, line_m) / 2.0))


@dataclass(frozen=True)
class AutofireSingleTargetOutcome:
    """Result of a single-target Autofire attack."""
    hit: bool
    margin: int             # only meaningful if hit (negative if miss)
    hit_count: int          # 1 + (margin // 2), capped at autofire_shots
    autofire_shots: int     # the shots fired


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
    line_penalty: int       # -1 OCV per 2m of the WHOLE line


def resolve_autofire_single_target(
    *,
    attacker_ocv: int,
    target_dcv: int,
    attacker_roll: int,
    autofire_shots: int,
) -> AutofireSingleTargetOutcome:
    """A single-target burst from bare numbers (6E2 p.44)."""
    if autofire_shots < 1:
        raise ValueError("autofire_shots must be >= 1")
    margin = (attacker_ocv + 11 - attacker_roll) - target_dcv
    hits = burst_hits(margin, autofire_shots)
    return AutofireSingleTargetOutcome(
        hit=hits > 0, margin=margin, hit_count=hits,
        autofire_shots=autofire_shots,
    )


def resolve_autofire_multi_target(
    *,
    attacker_ocv: int,
    targets: list[MultiTargetSpec],
    attacker_rolls: list[int],
    autofire_shots: int,
) -> list[MultiTargetHit]:
    """A multi-target burst from bare numbers (6E2 p.44): one roll per
    target, each at the whole line's penalty."""
    if len(targets) != len(attacker_rolls):
        raise ValueError("targets and attacker_rolls must have the same length")
    line_m = sum(max(0.0, t.distance_to_prev_m) for t in targets[1:])
    if shots_for_line(len(targets), line_m) > autofire_shots:
        raise ValueError(
            f"cannot fire at {len(targets)} targets along {line_m:g}m "
            f"with only {autofire_shots} shots"
        )
    penalty = line_penalty(line_m)
    results: list[MultiTargetHit] = []
    for spec, roll in zip(targets, attacker_rolls):
        effective_ocv = attacker_ocv + penalty
        margin = (effective_ocv + 11 - roll) - spec.target_dcv
        results.append(MultiTargetHit(
            target_id=spec.target_id, hit=margin >= 0, margin=margin,
            effective_ocv=effective_ocv, line_penalty=penalty,
        ))
    return results
