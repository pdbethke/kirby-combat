"""Close and Strike — get in fast, hit hard.

When a combatant's best attack is melee, the correct opening play is to
close the distance and hit.  Half-move to get adjacent, then swing with
the strongest HTH or HKA.  If already adjacent, skip the move and
strike immediately.

Preconditions:
  * Actor's best attack (highest damage_dice) is melee (range_m == 0
    or uses_str True with no range).

The STR-based strike through ``actor.attacks`` already reflects the
STR/5 damage dice contribution, so a 40 STR combatant shows 8d6 for
their unarmed strike and 12d6 for a levels=4 HANDTOHANDATTACK — that
is the comparison baseline.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.catalog._filters import _best_attack, _is_melee
from kirby_combat.tactics.library import register


@register
class CloseAndStrike(Tactic):
    name = "close_and_strike"
    basis = Basis(judgement="closing and striking in one phase denies the target a phase to retreat")
    priority = 38
    narrative_summary = (
        "Your strongest attack is melee range. Close the distance fast — "
        "half-move to get adjacent, then hit with everything. "
        "Don't waste a phase waiting for them to come to you. "
        "Once adjacent use your hardest hitting power each phase. "
        "If enemies are spread, target the most dangerous one first."
    )

    def applicable(self, situation: Situation) -> bool:
        best = _best_attack(situation)
        if best is None:
            return False
        return _is_melee(best)

    def execute(self, situation: Situation) -> Plan:
        best = _best_attack(situation)
        # The most dangerous enemy, not the first listed --- same
        # correction `keep_range` took today.
        threat = situation.threat
        target = (max(situation.enemies, key=lambda e: threat.get(e.id, 0.0))
                  if situation.enemies else None)
        target_id = target.id if target else None
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Best attack is melee ({best.name}, {best.damage_dice}d6, "
                f"range_m={best.range_m}). Close immediately and strike."
            ),
            steps=[
                # CLOSING IS A STEP, not a note. This plan used to be one
                # step, `kind="attack"`, with the closing described in
                # prose ("Half-move to get adjacent, then strike... If
                # already adjacent, skip the move") and in a
                # `close_first` param. Nothing read either. Attack offers
                # are gated by REACH, so a melee fighter whose enemy is at
                # range had no attack on the menu, this tactic matched
                # nothing and fell through --- and Power Lad stood two
                # metres from the last Cowboy doing nothing until the
                # stalemate guard fired.
                #
                # `move_strike` is the engine's own word for closing and
                # hitting in one action; he killed five men with it in the
                # same fight.
                PlanStep(
                    kind="move_strike",
                    target_id=target_id,
                    power_xmlid=best.xmlid,
                    notes="Close and strike in one action.",
                ),
                # And the plain strike for when he is already in reach,
                # where closing is not on the menu at all.
                PlanStep(
                    kind="attack",
                    target_id=target_id,
                    power_xmlid=best.xmlid,
                    notes="Already adjacent — strike.",
                ),
                # AND SIMPLY WALKING, when the gap is too wide for either.
                # Measured: Power Lad's claws were ON and the nearest
                # Cowboy stood 7.8m away against an 8m run, so `attack`
                # was gated by reach (1m) and `move_strike` by the half
                # move a strike leaves him (4m) --- both correctly. His
                # menu held four `move` offers and no tactic matched, so
                # the fallback aimed thirty-eight times while a monster
                # and a gunman stood looking at each other.
                #
                # Last, deliberately: spending a whole Phase walking is
                # what you do when you cannot do anything better.
                PlanStep(
                    kind="move",
                    target_id=target_id,
                    notes="Too far to strike at all — close the distance.",
                ),
            ],
            expected_outcome=(
                f"{best.damage_dice}d6 landing this phase. Enemy must absorb "
                "or abort — either outcome is advantageous."
            ),
        )
