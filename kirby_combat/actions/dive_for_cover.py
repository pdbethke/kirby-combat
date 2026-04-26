"""Dive for Cover — reactive abort; DEX Roll determines outcome.

Per 6E2 p87 §Using Dive For Cover:
    - Successful Dive: character ends Phase PRONE at chosen destination,
      at HALF DCV (until next Phase).
        - Against an Area-of-Effect attack: target hex is no longer
          occupied, so the Dive avoids the AoE entirely if the
          destination is OUTSIDE the AoE radius.
        - Against a non-Area attack: the Dive succeeds → the attacker's
          attack misses outright.
    - Failed Dive: character is at HALF DCV but did NOT move, AND the
      attacker gets +2 OCV against the diver this Phase.

The DEX Roll is the standard HERO Skill Roll: 3d6 ≤ 9 + DEX // 3.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import AbortDeclared
from kirby_combat.actions.reactive.abort import mark_aborting


# 6E2 p87: a successful Dive ends in PRONE at the chosen destination
# at HALF DCV until next Phase. A failure: half DCV, no movement, +2 OCV
# to attacker.
_HALF_DCV = 0.5
_FAILED_ATTACKER_OCV_BONUS = 2


@dataclass(frozen=True)
class DiveForCoverResult:
    """Outcome of resolving the Dive for Cover DEX roll.

    Per 6E2 p87:
        - On success: diver is prone at destination, at half DCV; AoE
          attacks miss if destination is outside the AoE.
        - On failure: diver is prone at half DCV, did not move, attacker
          gets +2 OCV.
    """
    success: bool
    roll: int                                # 3d6 sum
    target: int                              # the number the roll had to meet (≤ target)
    diver_prone: bool                        # always True after a Dive (success or fail)
    diver_dcv_factor: float                  # 0.5 (half DCV) per RAW
    attacker_ocv_bonus: int                  # +2 if dive failed; 0 if successful
    avoids_aoe: bool                         # True iff dive succeeded AND destination outside AoE
    destination: tuple[float, float, float] | None   # (x,y,z) if moved; None if didn't move


class DiveForCover:
    """Dive for Cover reactive abort.

    Declares an abort via the existing abort machinery, then the DEX Roll
    determines whether the dive succeeds (move + prone + ½ DCV) or fails
    (no movement + prone + ½ DCV + attacker gets +2 OCV).

    DEX Roll formula (HERO standard Skill Roll): 3d6 ≤ 9 + DEX // 3.
    """

    name: str = "dive_for_cover"

    @staticmethod
    def declare(
        session: CombatSession, combatant_id: str
    ) -> tuple[CombatSession, AbortDeclared]:
        """Declare Dive for Cover for this combatant.

        Reuses the abort machinery (same as Dodge/Block). Forfeits next phase.
        """
        return mark_aborting(session, combatant_id, to_action="dive_for_cover")

    @staticmethod
    def resolve_dex_roll(
        combatant_dex: int,
        dice: list[int],
        *,
        requested_destination: tuple[float, float, float] | None = None,
        attack_is_aoe: bool = False,
        aoe_origin: tuple[float, float, float] | None = None,
        aoe_radius_m: float | None = None,
    ) -> DiveForCoverResult:
        """Resolve the 3d6 DEX Roll for Dive for Cover per 6E2 p87.

        Args:
            combatant_dex: The diver's DEX characteristic.
            dice: List of three die results (each 1-6).
            requested_destination: Where the diver wants to end up if
                successful. Required if attack_is_aoe is True.
            attack_is_aoe: True if the incoming attack is an Area-of-Effect.
            aoe_origin: (x,y,z) origin of the AoE (centre).
            aoe_radius_m: Radius of the AoE.

        Returns:
            DiveForCoverResult with outcome details. Per 6E2 p87:
              - Success: diver is prone at destination, at half DCV;
                attacker's non-AoE attack misses; AoE misses iff
                destination outside aoe_radius from aoe_origin.
              - Failure: diver is prone at half DCV, did NOT move,
                attacker gets +2 OCV against the diver this Phase.
        """
        target = 9 + (combatant_dex // 3)
        roll = sum(dice)
        success = roll <= target

        if success:
            destination = requested_destination
            avoids_aoe = False
            if attack_is_aoe and requested_destination is not None and aoe_origin is not None and aoe_radius_m is not None:
                dx = requested_destination[0] - aoe_origin[0]
                dy = requested_destination[1] - aoe_origin[1]
                dz = requested_destination[2] - aoe_origin[2]
                dist_sq = dx * dx + dy * dy + dz * dz
                avoids_aoe = dist_sq > (aoe_radius_m * aoe_radius_m)
            return DiveForCoverResult(
                success=True,
                roll=roll,
                target=target,
                diver_prone=True,
                diver_dcv_factor=_HALF_DCV,
                attacker_ocv_bonus=0,
                avoids_aoe=avoids_aoe,
                destination=destination,
            )

        # Failed Dive: prone, ½ DCV, didn't move, attacker +2 OCV.
        return DiveForCoverResult(
            success=False,
            roll=roll,
            target=target,
            diver_prone=True,
            diver_dcv_factor=_HALF_DCV,
            attacker_ocv_bonus=_FAILED_ATTACKER_OCV_BONUS,
            avoids_aoe=False,
            destination=None,
        )
