"""Timeline — SPD-chart phase resolution + acting order for a segment."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping

from kirby_combat.models import StatBlockCombatant
from kirby_combat.session.tie_rule import TieRule, dex_roll_target
from kirby_combat.tables import segments_for_spd
from kirby_combat.talents.lightning_reflexes import (
    bonus_for_grants,
    lightning_reflexes_grants,
)


@dataclass
class ActionIntent:
    """What a combatant is about to do, as declared before final ordering.

    `is_mental` makes a mental action order on EGO rather than DEX (APG
    p.50, see `ordering_value`); `elect_lightning_reflexes` makes Lightning
    Reflexes raise effective DEX for the specific action it was bought for
    (6E1 p.116, see `ordering_value` and `talents/lightning_reflexes.py`).
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
    #: Lightning Reflexes (6E1 p.116), captured from the combatant's BUILD at
    #: provisional-order time -- not applied yet, because whether any grant
    #: here actually applies depends on the declared ActionIntent, which
    #: isn't known until `resolve_acting_order`. See `ordering_value`, which
    #: is where a matching grant turns into effective DEX.
    lightning_reflexes_grants: tuple = ()


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
    default -- `TieRule.DEX_ROLL` implements the roll, and this ladder is
    one setting of a campaign `TieRule` (`TieRule.INT_THEN_PRE`). This
    function's return value only matters for that setting; a deterministic
    order is what the test suite depends on.

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
    rather than DEX (APG p.50), and Lightning Reflexes raises effective DEX
    only for the specific action it was bought for (6E1 p.116) -- neither of
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
            # Lightning Reflexes (6E1 p.116) is BUILD data (levels, bought
            # scope) -- read it now, while `c` is in hand, so `ordering_value`
            # doesn't need a participant reference later (see ActingSlot's
            # `lightning_reflexes_grants` docstring). `hero` is absent on a
            # flat StatBlockCombatant, so this is a no-op there.
            hero = getattr(c, "hero", None)
            grants = lightning_reflexes_grants(hero) if hero is not None else ()
            slots.append(
                ActingSlot(
                    combatant_id=c.id,
                    segment=segment,
                    dex_at_phase=stats.dex,
                    int_tiebreak=int_tiebreak,
                    pre_tiebreak=pre_tiebreak,
                    ego=stats.ego,
                    has_acted=False,
                    lightning_reflexes_grants=grants,
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

    Non-mental slots order on `dex_at_phase` PLUS Lightning Reflexes' bonus
    (6E1 p.116) when the intent elected it (`ActionIntent.
    elect_lightning_reflexes`) and the combatant's bought scope covers this
    action (`ActingSlot.lightning_reflexes_grants`, captured at provisional
    time -- see `build_provisional_order_for_segment`). An intent-less slot
    gets no bonus: electing the bonus is the whole point (6E1 p.116(c) --
    it costs the rest of the Phase), so it is never applied silently.

    This is initiative ONLY -- it must never reach `dex_roll_target`
    (session/tie_rule.py), which 6E1 p.116 requires stay on printed DEX
    ("his Agility Skill Rolls remain 12-").

    A mental intent never gets the Lightning Reflexes bonus applied here,
    even when elected and even when the build has a matching grant --
    ordering runs on EGO instead. `talents/lightning_reflexes.py`'s
    `restriction_for_slot` mirrors this exact rule (via
    `_bonus_applied_by_ordering`) before enforcing 6E1 p.116(c)'s Phase
    forfeiture, so a mental actor who elected the bonus is never
    restricted for a bonus that was never actually applied.
    """
    if slot.intent is not None and slot.intent.is_mental:
        return slot.ego
    bonus = 0
    if slot.intent is not None and slot.intent.elect_lightning_reflexes:
        bonus = bonus_for_grants(
            slot.lightning_reflexes_grants, slot.intent.action_type)
    return slot.dex_at_phase + bonus


def resolve_acting_order(
    slots: list[ActingSlot],
    intents: dict[str, "ActionIntent"],
    *,
    tie_rule: TieRule = TieRule.INT_THEN_PRE,
    roller: Callable[[], int] | None = None,
    acts_first: Mapping[str, str] | None = None,
) -> list[ActingSlot]:
    """Resolve a provisional order into the final acting order for a segment.

    `acts_first` maps blocker_id -> attacker_id: a successful Block (6E2
    p.60, "ACTING FIRST") lets the blocker "act first (regardless of
    relative DEX)" in the next Segment where both his Phase and the
    attacker's Phase fall -- and the book is explicit this holds "even if
    [the attacker] does not attack again", so it is consulted purely off
    who has a Phase this Segment, never off `intents`. A pair only takes
    priority when BOTH the blocker and the named attacker have a slot in
    `slots` this Segment (that is the "same Segment" condition the rule
    states); an entry naming a combatant absent this Segment is inert here
    -- see `consume_block_priority` for when such an entry is spent.
    Block priority is implemented here as an ABSOLUTE leading sort key,
    checked before `ordering_value` is even read -- it outranks the mental
    EGO ordering and the INT/PRE tie ladder for every combatant with a
    Phase this Segment, not only against the named attacker. 6E2 p.60 only
    says the blocker acts "regardless of relative DEX", which reads
    pairwise against the attacker; the books do not settle whether the
    priority is pairwise (only leapfrogs the named attacker) or absolute
    (leapfrogs everyone, including uninvolved third parties). This engine
    implements the absolute reading -- a true pairwise priority is a
    partial order, not expressible as a single sort key, and reworking
    this into one is session-driver work, out of scope here. See
    `tests/session/test_timeline.py::
    test_block_priority_leapfrogs_an_uninvolved_third_party` for the
    concrete case this decision produces.

    `intents` maps combatant_id -> ActionIntent for combatants who have
    declared what they're about to do; a combatant absent from `intents`
    sorts exactly as it does today (on printed DEX with `tie_rule` breaking
    ties). For a combatant who *does* have a declared intent,
    `is_mental`/`elect_lightning_reflexes` change the sort key via
    `ordering_value` -- see that function's docstring.

    Ordering: the leading key is Block priority (above); within that,
    `ordering_value` decides (printed DEX, or EGO for a declared mental
    action, plus any applied Lightning Reflexes bonus); DEX ties are then
    broken per `tie_rule` -- 6E2 p.21's default is a contested DEX Roll
    (TieRule.DEX_ROLL); the GM's stated alternative is highest INT then PRE
    (TieRule.INT_THEN_PRE, "the character with the highest INT acts first
    (if their INTs are also tied, use PRE)"); TieRule.RANDOM is not from
    the books -- it is the campaign option the engine already declared as
    `template.randomize_dex_ties` and never wired up. Remaining ties fall
    back to stable ordering by combatant_id.

    `tie_rule` defaults to INT_THEN_PRE here -- not the campaign's book
    default of DEX_ROLL -- so existing callers/tests that don't pass a
    roller stay deterministic. The campaign-facing default lives on
    CombatTemplate.tie_rule (template.py); DORMANT -- no caller plumbs that
    field into this function's `tie_rule` argument today, so a GM changing
    it on a template has no effect until a session driver wires the two
    together (see the DORMANT note on that field for detail).

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
            lightning_reflexes_grants=s.lightning_reflexes_grants,
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

    # Block priority (6E2 p.60), as this engine implements it (absolute,
    # not pairwise -- see this function's docstring), must be the LEADING
    # sort key -- ahead of `ordering_value` (which is itself ahead of the
    # INT/PRE tie ladder). 0 sorts before 1, so a combatant with a
    # live priority against someone also acting this Segment goes first;
    # everyone else (including a blocker whose named attacker has no Phase
    # this Segment) ties at rank 1 and falls through to the normal ladder.
    acts_first = acts_first or {}
    ids_present = {s.combatant_id for s in slots}

    def _block_priority_rank(combatant_id: str) -> int:
        target = acts_first.get(combatant_id)
        return 0 if (target is not None and target in ids_present) else 1

    # Primary ordering: `ordering_value` (APG p.50 -- EGO for a declared
    # mental action, printed DEX otherwise, see that function's docstring).
    # DEX-tie tie-breaking (INT/PRE ladder, DEX Roll, RANDOM) is unchanged
    # by this and still keys off printed DEX/`dex_at_phase` -- APG p.50
    # only relocates who's compared on what for the *primary* sort.
    if tie_rule is TieRule.INT_THEN_PRE:
        key = lambda s: (_block_priority_rank(s.combatant_id), -ordering_value(s),
                          -s.int_tiebreak, -s.pre_tiebreak, s.combatant_id)
    elif tie_rule in (TieRule.DEX_ROLL, TieRule.RANDOM):
        key = lambda s: (_block_priority_rank(s.combatant_id), -ordering_value(s),
                          -tie_scores[s.combatant_id], s.combatant_id)
    else:
        raise ValueError(f"unknown TieRule: {tie_rule!r}")

    slots.sort(key=key)
    return slots


def build_acting_order_for_segment(
    combatants: Iterable[StatBlockCombatant],
    segment: int,
    tie_rule: TieRule = TieRule.INT_THEN_PRE,
    roller: Callable[[], int] | None = None,
    acts_first: Mapping[str, str] | None = None,
) -> list[ActingSlot]:
    """Thin wrapper: provisional order, then resolve with no declared intents.

    Kept for existing callers that only need a final order and have no
    intents to declare. See `build_provisional_order_for_segment` and
    `resolve_acting_order` for the two-phase split this wraps.

    `acts_first` (6E2 p.60) is forwarded to `resolve_acting_order` as-is
    and is read-only here -- this function never mutates it. A Segment
    can spend an `acts_first` entry (see `resolve_acting_order`'s
    docstring for the "same Segment" condition); callers who need to know
    which entries were spent so the priority doesn't outlive its one
    shared Segment must call `consume_block_priority` themselves with this
    call's `segment` and the combatants passed in -- consumption is a
    session-state concern, not something this ordering primitive decides
    on your behalf by rewriting an argument you handed it.
    """
    provisional = build_provisional_order_for_segment(combatants, segment)
    return resolve_acting_order(
        provisional, intents={}, tie_rule=tie_rule, roller=roller,
        acts_first=acts_first,
    )


def consume_block_priority(
    acts_first: Mapping[str, str],
    combatants: Iterable[StatBlockCombatant],
    segment: int,
) -> dict[str, str]:
    """Spend any `acts_first` (6E2 p.60) entries usable in `segment`.

    6E2 p.60: a successful Block's "act first" priority is good for the
    next Segment in which both the blocker's and the attacker's Phases
    fall -- one shared Segment, not a standing advantage. This holds
    "even if [the attacker] does not attack again", so an entry is spent
    purely by both ids having a Phase in `segment`, independent of what
    either combatant declares doing there.

    Returns a NEW dict with every entry whose blocker and named attacker
    both have a Phase in `segment` removed; entries where one side (or
    both) has no Phase this Segment are carried forward untouched, because
    the priority hasn't had its shared Segment yet. The input mapping is
    never mutated -- callers who want the priority to persist across
    Segments own that state themselves (e.g. on `Timeline`) and replace it
    with this function's return value; nothing here reaches into a
    caller-supplied dict as a side channel.
    """
    ids_in_segment = {
        c.id for c in combatants
        if segment in segments_for_spd(c.combat_stats().spd)
    }
    return {
        blocker_id: attacker_id
        for blocker_id, attacker_id in acts_first.items()
        if not (blocker_id in ids_in_segment and attacker_id in ids_in_segment)
    }


def _sum_roll(roll: int | list[int] | tuple[int, ...]) -> int:
    """A roller may hand back a single die or a dice pool (e.g. 3d6);
    normalize either shape to a total."""
    if isinstance(roll, (list, tuple)):
        return sum(roll)
    return roll
