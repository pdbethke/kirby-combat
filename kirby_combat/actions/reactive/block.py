"""Block — opposed 3d6 OCV roll. On success, attack is negated."""
from __future__ import annotations

from dataclasses import dataclass

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import AbortDeclared
from kirby_combat.actions.reactive.abort import mark_aborting


@dataclass
class BlockResult:
    """Outcome of a Block resolution."""
    success: bool            # True = attack negated
    attacker_roll: int
    blocker_roll: int
    attacker_margin: int     # OCV + 11 - roll
    blocker_margin: int


class Block:
    """Reactive Block. Two-phase: declare then resolve on an incoming attack."""

    name: str = "block"

    @staticmethod
    def declare(session: CombatSession, combatant_id: str) -> tuple[CombatSession, AbortDeclared]:
        """Declare a Block for this combatant. Marks them as aborting."""
        return mark_aborting(session, combatant_id, to_action="block")

    @staticmethod
    def resolve(
        *,
        attacker_ocv: int,
        attacker_dice: list[int],
        blocker_ocv: int,
        blocker_dice: list[int],
    ) -> BlockResult:
        """Resolve an opposed 3d6 OCV roll.

        Each side computes margin = (OCV + 11 - roll). Higher margin wins.
        Ties go to the blocker (RAW 6E2 pg 56 — block succeeds on ties).
        """
        if len(attacker_dice) != 3 or len(blocker_dice) != 3:
            raise ValueError("block requires 3d6 rolls on both sides")
        attacker_roll = sum(attacker_dice)
        blocker_roll = sum(blocker_dice)
        attacker_margin = attacker_ocv + 11 - attacker_roll
        blocker_margin = blocker_ocv + 11 - blocker_roll
        return BlockResult(
            success=(blocker_margin >= attacker_margin),
            attacker_roll=attacker_roll,
            blocker_roll=blocker_roll,
            attacker_margin=attacker_margin,
            blocker_margin=blocker_margin,
        )
