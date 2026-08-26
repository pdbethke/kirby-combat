"""Timeline — SPD-chart phase resolution + acting order for a segment."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from kirby_combat.models import StatBlockCombatant
from kirby_combat.session.tie_rule import TieRule, dex_roll_target
from kirby_combat.tables import segments_for_spd


@dataclass
class ActingSlot:
    """One combatant's slot in a single segment's acting order."""
    combatant_id: str
    segment: int
    dex_at_phase: int
    int_tiebreak: int
    pre_tiebreak: int
    has_acted: bool = False


@dataclass
class HeldAction:
    """A declared 'I act when X happens' slot."""
    combatant_id: str
    declared_at_sequence: int
    trigger_description: str
    for_action_type: str | None  # None = TBD when released


@dataclass
class Timeline:
    """Mutable timeline state for a CombatSession."""
    turn: int
    segment: int
    acting_order: list[ActingSlot]
    current_slot_index: int
    held_actions: list[HeldAction] = field(default_factory=list)
    aborted_this_phase: set[str] = field(default_factory=set)


def _tie_key(c: StatBlockCombatant) -> tuple[int, int]:
    """The 6E2 p.21 tie ladder: highest INT first, then highest PRE.

    Quoting p.21: "the GM may dispense with the DEX Roll ... the character
    with the highest INT acts first (if their INTs are also tied, use PRE)".

    Note this is the book's *alternative* to a contested DEX Roll, not the
    default -- Task 3 adds the roll and makes this one setting of a
    campaign TieRule. Until then it stays the engine's behaviour, because
    it is what the engine already did (badly) and a deterministic order is
    what the test suite depends on.

    Read through combat_stats(): the flat and HD-shaped participants answer
    differently off the participant itself.
    """
    stats = c.combat_stats()
    return (stats.int_, stats.pre)


def build_acting_order_for_segment(
    combatants: Iterable[StatBlockCombatant],
    segment: int,
    tie_rule: TieRule = TieRule.INT_THEN_PRE,
    roller: Callable[[], int] | None = None,
) -> list[ActingSlot]:
    """Build the acting order for one segment.

    Combatants without a phase in this segment (per SPD chart) are excluded.
    Ordering: highest DEX first; DEX ties are broken per `tie_rule` --
    6E2 p.21's default is a contested DEX Roll (TieRule.DEX_ROLL); the GM's
    stated alternative is highest INT then PRE (TieRule.INT_THEN_PRE,
    "the character with the highest INT acts first (if their INTs are also
    tied, use PRE)"); TieRule.RANDOM is not from the books -- it is the
    campaign option the engine already declared as
    `template.randomize_dex_ties` and never wired up. Remaining ties fall
    back to stable ordering by combatant_id.

    `tie_rule` defaults to INT_THEN_PRE here -- not the campaign's book
    default of DEX_ROLL -- so existing callers/tests that don't pass a
    roller stay deterministic. The campaign-facing default lives on
    CombatTemplate.tie_rule (template.py), where a GM can see and change it.

    For TieRule.DEX_ROLL / TieRule.RANDOM, `roller` is called exactly once
    per combatant, in input order -- not once per sort comparison. A
    comparator that called `roller` from inside a pairwise `cmp` would
    consume the scripted rolls in whatever order the sort algorithm chose
    to compare elements, not the order a test (or a GM) expects them
    assigned; rolling once per combatant up front keeps the assignment
    deterministic and independent of the sort implementation.
    """
    slots: list[ActingSlot] = []
    tie_scores: dict[str, float] = {}
    for c in combatants:
        # Read via combat_stats() once per combatant, not `.dex`/`.spd`
        # directly: those flat attributes only exist on the
        # StatBlockCombatant shape, and reading them here is exactly the
        # no-op shim this task removes (session/ must work for the HD-shaped
        # participant too).
        stats = c.combat_stats()
        if segment in segments_for_spd(stats.spd):
            int_tiebreak, pre_tiebreak = _tie_key(c)
            slots.append(
                ActingSlot(
                    combatant_id=c.id,
                    segment=segment,
                    dex_at_phase=stats.dex,
                    int_tiebreak=int_tiebreak,
                    pre_tiebreak=pre_tiebreak,
                    has_acted=False,
                )
            )
            if tie_rule is TieRule.DEX_ROLL:
                if roller is None:
                    raise ValueError("TieRule.DEX_ROLL requires a roller callable")
                # 6E2 p.21: "The character who succeeds with his DEX Roll by
                # the most gets to act first" -- score is margin of success.
                tie_scores[c.id] = dex_roll_target(c) - _sum_roll(roller())
            elif tie_rule is TieRule.RANDOM:
                if roller is None:
                    raise ValueError("TieRule.RANDOM requires a roller callable")
                # Not a book rule -- the campaign option the engine already
                # declared as `template.randomize_dex_ties` and never wired up.
                tie_scores[c.id] = _sum_roll(roller())

    if tie_rule is TieRule.INT_THEN_PRE:
        key = lambda s: (-s.dex_at_phase, -s.int_tiebreak, -s.pre_tiebreak,
                          s.combatant_id)
    elif tie_rule in (TieRule.DEX_ROLL, TieRule.RANDOM):
        key = lambda s: (-s.dex_at_phase, -tie_scores[s.combatant_id],
                          s.combatant_id)
    else:
        raise ValueError(f"unknown TieRule: {tie_rule!r}")

    slots.sort(key=key)
    return slots


def _sum_roll(roll: int | list[int] | tuple[int, ...]) -> int:
    """A roller may hand back a single die or a dice pool (e.g. 3d6);
    normalize either shape to a total."""
    if isinstance(roll, (list, tuple)):
        return sum(roll)
    return roll
