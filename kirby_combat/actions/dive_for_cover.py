"""Dive for Cover — reactive abort; DEX roll for partial cover (6E2 pg 67)."""
from __future__ import annotations

from dataclasses import dataclass

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import AbortDeclared
from kirby_combat.actions.reactive.abort import mark_aborting

# Partial cover DCV bonus granted on a successful dive.
_COVER_DCV_BONUS = 2


@dataclass(frozen=True)
class DiveForCoverResult:
    """Outcome of resolving the Dive for Cover DEX roll."""
    success: bool
    roll: int           # Sum of the 3d6 rolled.
    target: int         # The number the roll had to meet or beat (≤ target).
    granted_prone: bool
    granted_partial_cover: bool


class DiveForCover:
    """Dive for Cover reactive abort.

    Declares an abort via the existing abort machinery, then the DEX roll
    result determines whether the combatant gains prone + partial cover (+2 DCV).

    DEX roll formula (HERO standard skill roll): 3d6 ≤ floor(DEX / 3) + 9.
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
    def resolve_dex_roll(combatant_dex: int, dice: list[int]) -> DiveForCoverResult:
        """Resolve the 3d6 DEX roll for Dive for Cover.

        Args:
            combatant_dex: The combatant's DEX characteristic.
            dice: List of three die results (each 1-6).

        Returns:
            DiveForCoverResult with outcome details.
        """
        target = 9 + (combatant_dex // 3)
        roll = sum(dice)
        success = roll <= target
        return DiveForCoverResult(
            success=success,
            roll=roll,
            target=target,
            granted_prone=success,
            granted_partial_cover=success,
        )
