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

    @staticmethod
    def acts_first_priority(
        result: BlockResult, blocker_id: str, attacker_id: str,
    ) -> dict[str, str]:
        """Record the "acts first" priority a successful Block earns.

        Per 6E2 p.60, "ACTING FIRST": a character who successfully Blocks
        an attack may "act first (regardless of relative DEX)" if his next
        Phase and the attacker's next Phase fall in the same Segment --
        and the same passage is explicit this holds "even if [the
        attacker] does not attack again", so it cannot be resolved as a
        reaction at attack time; it has to be carried forward as state
        until it is spent. This returns the `{blocker_id: attacker_id}`
        entry to merge into that carried state (the `acts_first` mapping
        consumed by `session.timeline.resolve_acting_order` /
        `build_acting_order_for_segment`, and spent via
        `consume_block_priority`), or `{}` if the Block failed.

        DORMANT RECORDING POINT, WIRED CONSUMPTION: the priority this
        method returns, once it exists on `Encounter.acts_first`, now
        flows through the driver correctly -- `Encounter.run_segment`
        forwards it into `resolve_acting_order` (so the blocker really
        does act first, 6E2 p.60) and spends it via
        `consume_block_priority` once the blocker and the named attacker
        have shared a Segment (see `Encounter.acts_first`'s field
        docstring). What remains unwired is getting a `BlockResult` to
        this method in the first place: `Block.resolve` still has no live
        caller in kirby_combat -- there is no `BlockResolved`-shaped
        event, and `apply_event` derives no session state from a Block
        outcome. So in a real fight today, nothing ever calls this method
        to produce an entry for `Encounter.acts_first` to carry; the
        moment a live caller starts calling `Block.resolve` and this
        method, the priority it records will already flow correctly
        through `run_segment` with no further wiring needed here.
        """
        if not result.success:
            return {}
        return {blocker_id: attacker_id}
