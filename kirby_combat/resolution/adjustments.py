"""Adjustment powers resolution — Aid, Drain, Transfer, Suppress, Absorption.

Per HERO 6E1. All formulas adjust Active Points divided by the
stat's cost-per-level. Fade rates default to 5 active points per turn; can
be bought up via advantages (out of scope — handled by cost engine, not
combat engine).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AdjustmentOutcome:
    """Result of an adjustment power's resolution."""
    delta: int                    # signed change to the stat (positive=buff, negative=debuff)
    fade_rate_per_turn: int       # 0 = does not fade (e.g. Suppress)
    is_sustained: bool = False    # True = attacker must pay END to maintain (Suppress)


def compute_aid(
    active_points_rolled: int,
    points_per_level: int,
    target_max_boost_cp: int,
) -> AdjustmentOutcome:
    """Aid: positive delta, fades at 5 AP/turn. Capped at target_max_boost_cp."""
    raw_delta = active_points_rolled // max(points_per_level, 1)
    clamped = min(raw_delta, target_max_boost_cp)
    return AdjustmentOutcome(delta=clamped, fade_rate_per_turn=5)


def compute_drain(
    active_points_rolled: int,
    points_per_level: int,
    target_current_value: int,
) -> AdjustmentOutcome:
    """Drain: negative delta capped by current value (cannot reduce below 0)."""
    raw_magnitude = active_points_rolled // max(points_per_level, 1)
    magnitude = min(raw_magnitude, target_current_value)
    return AdjustmentOutcome(delta=-magnitude, fade_rate_per_turn=5)


def compute_transfer(
    active_points_rolled: int,
    points_per_level: int,
    source_current_value: int,
    target_max_boost_cp: int,
) -> tuple[int, int]:
    """Transfer: drain from source, aid attacker. Returns (source_delta, attacker_delta)."""
    drain_out = compute_drain(active_points_rolled, points_per_level, source_current_value)
    transferred_magnitude = -drain_out.delta
    aid_to_attacker = min(transferred_magnitude, target_max_boost_cp)
    return drain_out.delta, aid_to_attacker


def compute_suppress(
    active_points_rolled: int,
    points_per_level: int,
    target_current_value: int,
) -> AdjustmentOutcome:
    """Suppress: negative delta, sustained while attacker pays END. No fade-return."""
    raw_magnitude = active_points_rolled // max(points_per_level, 1)
    magnitude = min(raw_magnitude, target_current_value)
    return AdjustmentOutcome(
        delta=-magnitude, fade_rate_per_turn=0, is_sustained=True,
    )


def compute_absorption(
    incoming_damage: int,
    absorption_max_cp: int,
    points_per_level: int,
    target_max_boost_cp: int,
) -> AdjustmentOutcome:
    """Absorption: converts incoming damage into stat boost, capped by power's CP max."""
    absorbed = min(incoming_damage, absorption_max_cp)
    boost = min(absorbed // max(points_per_level, 1), target_max_boost_cp)
    return AdjustmentOutcome(delta=boost, fade_rate_per_turn=5)
