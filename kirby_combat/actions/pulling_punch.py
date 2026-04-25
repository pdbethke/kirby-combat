"""Pulling a Punch — voluntary DC reduction (6E2 pg 80).

Pure function module. No event is emitted; the reduction is passed as a
parameter on the action declaration at attack-resolve time.
"""
from __future__ import annotations


def apply_pulling_punch(base_dc: int, reduction: int) -> int:
    """Return the actual DC after voluntary reduction.

    Args:
        base_dc: The attack's full DC.
        reduction: How much the attacker chose to pull. Negative values are
            treated as zero (cannot accidentally boost DC). Values exceeding
            base_dc are clamped (cannot pull below 0 DC).

    Returns:
        max(0, base_dc - max(0, reduction))
    """
    safe_reduction = max(0, reduction)
    return max(0, base_dc - safe_reduction)
