"""HERO System 6E combat status determination."""
from __future__ import annotations


def determine_status_changes(
    stun_before: int,
    stun_after: int,
    body_before: int,
    body_after: int,
    con: int,
    max_body: int,
) -> list[str]:
    """Determine which status conditions apply after an attack resolves.

    Checks are evaluated independently; multiple statuses may be returned
    from a single attack (e.g. Stunned + Knocked Out).

    Args:
        stun_before: Target's STUN immediately before this attack was applied.
        stun_after: Target's STUN after damage has been subtracted.
        body_before: Target's BODY immediately before this attack was applied.
        body_after: Target's BODY after damage has been subtracted.
        con: Target's CON characteristic (Stunned threshold).
        max_body: Target's maximum (starting) BODY (Death threshold denominator).

    Returns:
        A list of status-change strings, in the order: Stunned, Knocked Out, Dead.
        Returns an empty list when no thresholds are crossed.
    """
    statuses: list[str] = []

    stun_dealt = stun_before - stun_after

    # Stunned: single attack dealt more STUN than the target's CON
    if stun_dealt > con:
        statuses.append("Stunned")

    # Knocked Out: current STUN has fallen to zero or below
    if stun_after <= 0:
        statuses.append("Knocked Out")

    # Dead: BODY has fallen to −max_body or worse
    if body_after <= -max_body:
        statuses.append("Dead")

    return statuses
