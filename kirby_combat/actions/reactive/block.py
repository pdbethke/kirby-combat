"""Block — Attack Roll vs attacker's OCV. On success, attack is negated.

Per 6E2 p59 §Using Block:
    "To Block, a character makes an Attack Roll against the attacker's OCV"

The blocker rolls 3d6 and succeeds iff:
    blocker_OCV + 11 - blocker_roll >= attacker_OCV

The attacker's own to-hit roll is irrelevant to the Block test — the
attacker still rolls to-hit normally; the Block just intercepts on success.
"""
from __future__ import annotations

from dataclasses import dataclass

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import AbortDeclared
from kirby_combat.actions.reactive.abort import mark_aborting


@dataclass
class BlockResult:
    """Outcome of a Block resolution."""
    success: bool            # True = attack negated
    blocker_roll: int        # 3d6 sum
    blocker_margin: int      # blocker_ocv + 11 - blocker_roll - attacker_ocv
    attacker_ocv: int        # the value the blocker rolled against
    blocker_ocv: int


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
        blocker_ocv: int,
        blocker_dice: list[int],
        attacker_ocv: int,
    ) -> BlockResult:
        """Resolve a Block — single Attack Roll vs attacker's OCV.

        Per 6E2 p59: the blocker rolls 3d6 and succeeds iff
        (blocker_OCV + 11 - blocker_roll) >= attacker_OCV.
        """
        if len(blocker_dice) != 3:
            raise ValueError("block requires a 3d6 roll for the blocker")
        blocker_roll = sum(blocker_dice)
        blocker_margin = (blocker_ocv + 11 - blocker_roll) - attacker_ocv
        return BlockResult(
            success=(blocker_margin >= 0),
            blocker_roll=blocker_roll,
            blocker_margin=blocker_margin,
            attacker_ocv=attacker_ocv,
            blocker_ocv=blocker_ocv,
        )
