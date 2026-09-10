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
        A list of status-change strings, in the order: Stunned, Knocked
        Out, Dying, Dead. Returns an empty list when no thresholds are
        crossed.
    """
    statuses: list[str] = []

    stun_dealt = stun_before - stun_after

    # Stunned: single attack dealt more STUN than the target's CON
    if stun_dealt > con:
        statuses.append("Stunned")

    # Knocked Out: current STUN has fallen to zero or below
    if stun_after <= 0:
        statuses.append("Knocked Out")

    # Dead: BODY has fallen to −max_body or worse.
    # 6E2 p.109's own example: 10 BODY dies at −10, 8 BODY at −8.
    dead = body_after <= -max_body

    # Dying: "A character at or below 0 BODY is dying" (6E2 p.109), and
    # he loses 1 BODY each Turn until he is Dead or someone stops it ---
    # see `dying.bleed_out`, applied at the Post-Segment 12 hook the same
    # page puts it on.
    #
    # NOT KNOCKED OUT, and this is the distinction the engine was missing:
    # `is_down` folds "STUN <= 0 or BODY <= 0" into one boolean, which is
    # the right answer to "can he keep fighting" and the wrong DESCRIPTION
    # of what happened. 6E2 p.105: "A character can have 0 BODY or
    # negative BODY and still have lots of STUN --- he's dying, but awake
    # and active." A replay showed a man at 0 BODY badged only "KO".
    #
    # NOT ALSO DEAD. Past the threshold there is nothing left to bleed
    # out, and two mutually exclusive words on one status card help
    # nobody.
    if body_after <= 0 and not dead:
        statuses.append("Dying")

    if dead:
        statuses.append("Dead")

    return statuses
