"""Timeline — SPD-chart phase resolution + acting order for a segment."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from kirby_combat.models import StatBlockCombatant
from kirby_combat.session.tie_rule import TieRule, dex_roll_target
from kirby_combat.tables import segments_for_spd


@dataclass
class ActionIntent:
    """What a combatant is about to do, as declared before final ordering.

    Carried but not yet acted on: Task 6 gives `is_mental` meaning (mental
    actions order on EGO rather than DEX) and Task 7 gives
    `elect_lightning_reflexes` meaning (Lightning Reflexes raises effective
    DEX only for the specific action it was bought for). This task only
    threads the field through.
    """
    action_type: str
    is_mental: bool = False
    elect_lightning_reflexes: bool = False


@dataclass
class ActingSlot:
    """One combatant's slot in a single segment's acting order."""
    combatant_id: str
    segment: int
    dex_at_phase: int
    int_tiebreak: int
    pre_tiebreak: int
    ego: int
    has_acted: bool = False
    intent: ActionIntent | None = None


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


def build_provisional_order_for_segment(
    combatants: Iterable[StatBlockCombatant],
    segment: int,
) -> list[ActingSlot]:
    """Build the *provisional* acting order for one segment: printed DEX
    only, no tie-breaking.

    Combatants without a phase in this segment (per SPD chart) are excluded.
    This is a provisional pass because a final order can depend on what
    action a combatant is about to take -- mental actions order on EGO
    rather than DEX (Task 6), and Lightning Reflexes raises effective DEX
    only for the specific action it was bought for (Task 7) -- neither of
    which is knowable from stats alone. Feed this list's slots, together
    with any declared intents, to `resolve_acting_order` to get the final
    order (DEX ties included).

    `int_tiebreak`/`pre_tiebreak` are captured here (per 6E2 p.21's tie
    ladder) so `resolve_acting_order` can break ties without re-reading
    stats.

    Sorts on DEX ONLY (a stable sort, so combatants sharing a DEX keep
    their relative input order here). This matters beyond display: for
    TieRule.DEX_ROLL/RANDOM, `resolve_acting_order` rolls once per slot in
    the order this list hands them over, and that roll-consumption order
    must match `combatants`' input order for same-DEX combatants -- the
    same guarantee the old single-pass function made. Breaking ties on
    `combatant_id` here (instead of leaving them in input order) would
    reshuffle who gets which scripted roll and could flip who wins a DEX
    tie -- a real ordering-outcome change, not just cosmetic. Final
    determinism (a stable, id-ordered output) is `resolve_acting_order`'s
    job, not this pass's.
    """
    slots: list[ActingSlot] = []
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
                    ego=stats.ego,
                    has_acted=False,
                )
            )

    slots.sort(key=lambda s: -s.dex_at_phase)
    return slots


def ordering_value(slot: "ActingSlot") -> int:
    """The characteristic a slot's *acting order* is decided on.

    APG p.50: mental combat and mental powers "use EGO to determine who
    acts first" -- so a mental action orders on EGO, not DEX, even though
    the same combatant's physical actions in another segment still order
    on DEX. Whether a given slot is a mental action is per-declared-intent
    (`ActionIntent.is_mental`), not per-combatant: a telepath throwing a
    punch still orders on DEX.

    Non-mental (or intent-less) slots order on `dex_at_phase`, which today
    is always printed DEX. Task 7 will make this branch return *effective*
    DEX (printed DEX plus Lightning Reflexes) for the specific action it
    was bought for -- this is the one place that change lands; nothing
    here anticipates it further.
    """
    if slot.intent is not None and slot.intent.is_mental:
        return slot.ego
    return slot.dex_at_phase


def resolve_acting_order(
    slots: list[ActingSlot],
    intents: dict[str, "ActionIntent"],
    *,
    tie_rule: TieRule = TieRule.INT_THEN_PRE,
    roller: Callable[[], int] | None = None,
) -> list[ActingSlot]:
    """Resolve a provisional order into the final acting order for a segment.

    `intents` maps combatant_id -> ActionIntent for combatants who have
    declared what they're about to do; a combatant absent from `intents`
    sorts exactly as it does today (on printed DEX with `tie_rule` breaking
    ties). Tasks 6/7 will make `is_mental`/`elect_lightning_reflexes` change
    the sort key for combatants who *do* have a declared intent; until then
    an intent's presence changes nothing, so this pass is a true no-op over
    the provisional order.

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
    slots = [
        ActingSlot(
            combatant_id=s.combatant_id,
            segment=s.segment,
            dex_at_phase=s.dex_at_phase,
            int_tiebreak=s.int_tiebreak,
            pre_tiebreak=s.pre_tiebreak,
            ego=s.ego,
            has_acted=s.has_acted,
            intent=intents.get(s.combatant_id),
        )
        for s in slots
    ]

    tie_scores: dict[str, float] = {}
    if tie_rule is TieRule.DEX_ROLL:
        for s in slots:
            if roller is None:
                raise ValueError("TieRule.DEX_ROLL requires a roller callable")
            # 6E2 p.21: "The character who succeeds with his DEX Roll by
            # the most gets to act first" -- score is margin of success.
            # `dex_at_phase` is printed DEX as captured by
            # `build_provisional_order_for_segment`, satisfying
            # `dex_roll_target`'s "callers MUST pass printed DEX" contract.
            tie_scores[s.combatant_id] = dex_roll_target(s.dex_at_phase) - _sum_roll(roller())
    elif tie_rule is TieRule.RANDOM:
        for s in slots:
            if roller is None:
                raise ValueError("TieRule.RANDOM requires a roller callable")
            # Not a book rule -- the campaign option the engine already
            # declared as `template.randomize_dex_ties` and never wired up.
            tie_scores[s.combatant_id] = _sum_roll(roller())

    # Primary ordering: `ordering_value` (APG p.50 -- EGO for a declared
    # mental action, printed DEX otherwise, see that function's docstring).
    # DEX-tie tie-breaking (INT/PRE ladder, DEX Roll, RANDOM) is unchanged
    # by this and still keys off printed DEX/`dex_at_phase` -- APG p.50
    # only relocates who's compared on what for the *primary* sort.
    if tie_rule is TieRule.INT_THEN_PRE:
        key = lambda s: (-ordering_value(s), -s.int_tiebreak, -s.pre_tiebreak,
                          s.combatant_id)
    elif tie_rule in (TieRule.DEX_ROLL, TieRule.RANDOM):
        key = lambda s: (-ordering_value(s), -tie_scores[s.combatant_id],
                          s.combatant_id)
    else:
        raise ValueError(f"unknown TieRule: {tie_rule!r}")

    slots.sort(key=key)
    return slots


def build_acting_order_for_segment(
    combatants: Iterable[StatBlockCombatant],
    segment: int,
    tie_rule: TieRule = TieRule.INT_THEN_PRE,
    roller: Callable[[], int] | None = None,
) -> list[ActingSlot]:
    """Thin wrapper: provisional order, then resolve with no declared intents.

    Kept for existing callers that only need a final order and have no
    intents to declare. See `build_provisional_order_for_segment` and
    `resolve_acting_order` for the two-phase split this wraps.
    """
    provisional = build_provisional_order_for_segment(combatants, segment)
    return resolve_acting_order(
        provisional, intents={}, tie_rule=tie_rule, roller=roller
    )


def _sum_roll(roll: int | list[int] | tuple[int, ...]) -> int:
    """A roller may hand back a single die or a dice pool (e.g. 3d6);
    normalize either shape to a total."""
    if isinstance(roll, (list, tuple)):
        return sum(roll)
    return roll
