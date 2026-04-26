"""Pulling A Punch — voluntary damage reduction with OCV cost.

Per 6E2 p89 §Pulling A Punch:
    - Apply -1 OCV per 5 DCs (or 5d6) of attack pulled.
    - Maximum DCs pulled: half the attack's DCs.
    - The pulled punch does HALF BODY (full STUN).
    - If the Attack Roll succeeds EXACTLY (margin == 0), the pull is
      forfeited and full damage applies.

Pure function module. No event is emitted; the caller applies the OCV
modifier and the body multiplier at attack-resolve time.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PulledPunchOutcome:
    """Result of attempting to pull a punch.

    Per 6E2 p89: pulling reduces BODY (not DCs), at a cost of -1 OCV per
    5 DCs pulled. Rolling the Attack Roll exactly (margin == 0) forfeits
    the pull and full damage applies.
    """
    ocv_modifier: int            # negative; -1 per 5 DCs pulled
    body_multiplier: float       # 0.5 if pulled (and not exact-match), 1.0 otherwise
    stun_multiplier: float       # 1.0 (STUN unaffected by pulling)
    dcs_pulled: int              # how many DCs were declared as pulled (after capping)
    rolled_exactly: bool         # if True, the pull is overridden by RAW


def resolve_pulled_punch(
    *,
    base_dcs: int,
    dcs_pulled: int,
    rolled_exactly: bool = False,
) -> PulledPunchOutcome:
    """Compute the OCV penalty and damage modifiers for a Pulled Punch.

    Args:
        base_dcs: Total DCs of the attack before pulling.
        dcs_pulled: How many DCs the attacker chose to pull. Capped at
            base_dcs // 2 (RAW max). Negative values clamp to 0.
        rolled_exactly: If True, the attacker's Attack Roll exactly hit
            the target's DCV (margin == 0) — RAW says the pull is
            forfeited and full damage applies.

    Returns:
        PulledPunchOutcome with the OCV modifier (caller applies to to-hit
        roll) and the body_multiplier (caller multiplies BODY damage by).
    """
    base_dcs = max(0, base_dcs)
    # Cap at half the attack's DCs per 6E2 p89.
    max_pull = base_dcs // 2
    dcs_pulled = max(0, min(dcs_pulled, max_pull))
    # -1 OCV per 5 full DCs pulled (integer division — 4 DCs costs 0 OCV,
    # 5 DCs costs 1 OCV).
    ocv_modifier = -(dcs_pulled // 5)

    if rolled_exactly:
        # Per 6E2 p89: rolling the Attack Roll exactly forfeits the pull.
        # OCV cost remains (the attacker chose to pull); damage is full.
        return PulledPunchOutcome(
            ocv_modifier=ocv_modifier,
            body_multiplier=1.0,
            stun_multiplier=1.0,
            dcs_pulled=dcs_pulled,
            rolled_exactly=True,
        )

    body_multiplier = 0.5 if dcs_pulled > 0 else 1.0
    return PulledPunchOutcome(
        ocv_modifier=ocv_modifier,
        body_multiplier=body_multiplier,
        stun_multiplier=1.0,
        dcs_pulled=dcs_pulled,
        rolled_exactly=False,
    )
