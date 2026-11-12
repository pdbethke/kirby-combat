"""Framework state — which Multipower slots are active, folded from the log.

`enumerate_actions` takes `slot_allocation` as a PARAMETER: the active set
has always been the caller's to hold, because no combatant in this engine
has a field for it. That is a reasonable split --- a framework's reserve is
build data --- but it left the caller tracking something the fight changes,
with nothing to read it back from.

`active_slots` closes that: a `reallocate` records the new set on the log,
and this folds the latest one forward per framework.

`allocation_for` goes the rest of the way. The reserve and the per-slot
costs were never really the caller's either --- they are build data, and
`HeroCombatant.framework_view()` has always exposed them --- so it assembles
the whole `slot_allocation` mapping `enumerate_actions` wants, from the
build plus the log. A caller may still pass its own; what it no longer has
to do is keep one in step with a fight it is not otherwise tracking.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.models import FrameworkView
    from kirby_combat.session.combat_session import CombatSession


def framework_id_of(action_id: str) -> str:
    """The framework id an offer's action_id names, or ``""`` for anything
    else, so a caller can refuse rather than act on a framework it could
    not identify.

    The shapes enumeration writes (the second segment is always the
    framework)::

        reallocate_slots:<framework_id>:split
        reconfigure_vpp:<framework_id>
    """
    parts = (action_id or "").split(":")
    if len(parts) < 2 or not parts[1]:
        return ""
    return parts[1]


def parse_reallocation(action_id: str) -> tuple[str, tuple[str, ...]]:
    """Read a framework id and the slot ids an OLD-STYLE offer lists.

    ``reallocate_slots:<framework_id>:<slot_id,slot_id,...>`` is the shape
    enumeration still writes until the split offers replace it; the
    resolver no longer accepts it (a split is stated in points, not as a
    set of slots: 6E1 p.404-406). Kept so enumeration's own tests can read
    what it offers; the resolver uses `framework_id_of` and `SplitChoice`.

    Returns ``("", ())`` for anything else.
    """
    framework_id = framework_id_of(action_id)
    if not framework_id:
        return "", ()
    parts = action_id.split(":")
    if len(parts) < 3 or not parts[2]:
        return framework_id, ()
    return framework_id, tuple(x for x in parts[2].split(",") if x)


def active_slots(
    session: "CombatSession", combatant_id: str, framework_id: str,
) -> tuple[str, ...]:
    """The slots this combatant has switched on for ``framework_id``: those
    holding points in his current split (6E1 p.404-406).

    Read from the folded `CombatantState.slot_points`, which the latest
    `SlotsAllocated` replaced whole --- the same absolute-value discipline
    `session/effects.py` requires of every state-changing event.

    Empty when the framework has not been opened, which means "no
    opinion", not "nothing active": the build's own default set is the
    caller's to supply.
    """
    combatant = session.combatants.get(combatant_id)
    if combatant is None:
        return ()
    split = combatant.state.slot_points.get(framework_id, {})
    return tuple(sid for sid, pts in split.items() if pts > 0)


def allocation_for(session: "CombatSession", actor) -> dict[str, tuple] | None:
    """The `slot_allocation` mapping `enumerate_actions` wants, assembled.

    Shape: ``framework_id -> (reserve, used_points, active_slot_ids,
    slot_costs)``. The reserve and the per-slot costs come from the BUILD
    (`framework_view()`); which slots are active comes from the LOG (the
    fight's own reallocations). Neither half was ever the caller's to
    invent, and keeping them in step by hand is what this removes.

    ``used_points`` is the total cost of the active slots --- the reserve a
    Multipower is currently drawing --- so the gate in `enumerate_actions`
    ("this slot costs more than what is left") reads a real remainder
    rather than assuming an empty framework.

    Returns ``None`` when the actor has no frameworks, which
    `enumerate_actions` reads as "no gate" --- the same thing a caller
    passing nothing has always meant.
    """
    views = list(getattr(actor, "framework_view", lambda: [])() or [])
    if not views:
        return None

    allocation: dict[str, tuple] = {}
    for view in views:
        slot_costs = {s.slot_id: int(s.active_points or 0) for s in view.slots}
        active = active_slots(session, actor.id, view.framework_id)
        # Fixed slots draw in full; a variable slot takes only what is left,
        # so the same accounting a split uses applies here --
        # a used total that charged variables at full cost would gate away
        # slots the reserve can actually carry.
        by_id = {s.slot_id: s for s in view.slots}
        reserve = int(view.reserve_or_pool or 0)
        used = sum(
            slot_costs.get(sid, 0) for sid in active
            if sid in by_id and not by_id[sid].variable
        )
        for sid in active:
            slot = by_id.get(sid)
            if slot is not None and slot.variable:
                used += min(int(slot.active_points or 0), max(0, reserve - used))
        allocation[view.framework_id] = (
            reserve, used, set(active), slot_costs,
        )
    return allocation


class ReserveExceeded(Exception):
    """A reallocation asked for more slots than the reserve can carry.

    6E1 p.404: a Multipower's reserve is the total Active Points its slots
    may draw AT ONCE. Switching on a set that costs more than the reserve is
    not a legal configuration --- it is the one thing the framework exists
    to constrain, and the whole reason a Multipower is cheaper than buying
    the powers outright.
    """

    def __init__(self, framework_id: str, requested: int, reserve: int) -> None:
        self.framework_id = framework_id
        self.requested = requested
        self.reserve = reserve
        super().__init__(
            f"framework {framework_id!r}: the requested slots draw "
            f"{requested} Active Points against a reserve of {reserve}"
        )


#: The tail of a split offer's id: ``reallocate_slots:<framework_id>:split``.
SPLIT_SUFFIX = "split"

#: Separates the slots a completed split names (``bolt@40+wind@20``); the
#: same join `adjustments.CharacteristicChoice` uses.
SPLIT_JOIN = "+"
#: Separates a slot id from its points inside one term.
SPLIT_AT = "@"


@dataclass(frozen=True)
class SlotTerms:
    """What a split needs to know about one slot (6E1 p.404-406).

    ``max_points`` is the slot's Active Points; ``steps`` the step sizes
    that decide a variable slot's effect (the points themselves need not
    sit on a step: p.406).
    """

    slot_id: str
    name: str
    variable: bool
    max_points: int
    steps: tuple[int, ...]


def _check_split(
    framework_id: str, reserve: int, terms: dict[str, SlotTerms],
    points: dict[str, int],
) -> int:
    """The one rule set a split is held to; returns the points drawn.

    6E1 p.404-405: a FIXED slot is on at its full Active Points or off. A
    VARIABLE slot takes any share of the reserve from 0 to its Active
    Points (p.405). p.404: the shares together may not exceed the reserve.
    Raises ``KeyError`` for a slot the framework lacks, ``ValueError`` for
    a share the slot's kind forbids, ``ReserveExceeded`` for an overdraw.
    """
    unknown = sorted(sid for sid in points if sid not in terms)
    if unknown:
        raise KeyError(f"framework {framework_id!r} has no slot(s) {unknown}")
    for sid, pts in points.items():
        t = terms[sid]
        if t.variable:
            if not 0 <= pts <= t.max_points:
                raise ValueError(
                    f"{t.name!r} is a variable slot of {t.max_points} Active "
                    f"Points; {pts} is outside 0..{t.max_points} (6E1 p.405)")
        elif pts not in (0, t.max_points):
            raise ValueError(
                f"{t.name!r} is a fixed slot: it is off (0) or on at its "
                f"full {t.max_points} Active Points, not {pts} (6E1 p.404-405)")
    drawn = sum(points.values())
    if drawn > reserve:
        raise ReserveExceeded(framework_id, drawn, reserve)
    return drawn


def validate_split(view: "FrameworkView", points: dict[str, int]) -> int:
    """Check a proposed split of ``view``'s reserve; returns the total drawn.

    6E1 p.404-406 (rules in `_check_split`); p.406: points need not sit on
    a step. ENFORCED, NOT ASSUMED: an offer is not a permission slip, so
    the resolver re-asks this of whatever id it is handed.
    """
    terms = {
        s.slot_id: SlotTerms(s.slot_id, s.name, bool(s.variable),
                             int(s.active_points or 0), ())
        for s in view.slots
    }
    return _check_split(view.framework_id, int(view.reserve_or_pool or 0),
                        terms, points)


@dataclass(frozen=True)
class SplitChoice:
    """What a Multipower's user states per split: points per slot.

    6E1 p.404-406: the reserve is divided among the slots, fixed ones whole
    or not at all, variable ones in any share. p.410: he may re-divide it
    as a Zero Phase Action, once a Phase. The offer stands for every legal
    split (`LegalAction.choice`) rather than one offer per division, which
    for a variable slot is unbounded; the seat answers the offer's id plus
    ``=<slot>@<points>+<slot>@<points>`` and `parse` holds the answer to
    the rule. Same shape as `adjustments.CharacteristicChoice`.

    ``current`` is the split in force ({} before the opening); answering
    with it changes nothing and is refused.
    """

    framework_id: str
    reserve: int
    slots: tuple[SlotTerms, ...]
    current: dict[str, int]

    def instructions(self) -> str:
        """How to answer, for the refusal a bare id earns."""
        names = ", ".join(f"{t.slot_id} ({'variable' if t.variable else 'fixed'}, "
                          f"{t.max_points})" for t in self.slots)
        return (f"=<slot>{SPLIT_AT}<points>{SPLIT_JOIN}... stating each slot's "
                f"points out of a reserve of {self.reserve}; slots: {names}")

    def answer(self, points: dict[str, int]) -> str:
        """The tail a seat appends to the offer id; slots at 0 are omitted."""
        return "=" + SPLIT_JOIN.join(
            f"{sid}{SPLIT_AT}{pts}" for sid, pts in points.items() if pts)

    def parse(self, tail: str) -> dict[str, int]:
        """The split an answer's tail states, over EVERY slot (0 = off), or
        ValueError saying which rule it breaks."""
        stated: dict[str, int] = {}
        for term in (t for t in tail.split(SPLIT_JOIN) if t):
            sid, at, raw = term.partition(SPLIT_AT)
            try:
                if not at:
                    raise ValueError
                pts = int(raw)
            except ValueError:
                raise ValueError(f"{term!r} is not <slot>{SPLIT_AT}<points>") from None
            if sid in stated:
                raise ValueError(f"names slot {sid!r} twice")
            stated[sid] = pts
        terms = {t.slot_id: t for t in self.slots}
        try:
            _check_split(self.framework_id, self.reserve, terms, stated)
        except (KeyError, ReserveExceeded) as exc:
            raise ValueError(str(exc.args[0] if isinstance(exc, KeyError) else exc)) from exc
        full = {sid: stated.get(sid, 0) for sid in terms}
        if full == {sid: self.current.get(sid, 0) for sid in terms}:
            raise ValueError("that is the split already in force; it changes nothing")
        return full


#: The menu kind that changes a Multipower's allocation.
REALLOCATE_KIND = "reallocate"


def reallocated_this_phase(session: "CombatSession", combatant_id: str) -> bool:
    """Has he already reallocated a Multipower in this Phase?

    6E1 p.410: "A character can change the way his Multipower reserve
    points are distributed or allocated as a Zero Phase Action. However,
    unless the GM permits otherwise, he may not distribute or allocate
    reserve points more than once in a Phase." The loop reads this to keep
    the Phase his after a reallocation and to take the offer off the menu
    when the same Phase comes back to him.
    """
    from kirby_combat.pre_attacks.in_the_phase import _in_this_phase

    return any(
        getattr(evt, "kind", None) == "ActionDeclared"
        and getattr(evt, "combatant_id", None) == combatant_id
        and getattr(evt, "action_type", None) == REALLOCATE_KIND
        for evt in _in_this_phase(session, combatant_id)
    )


def split_choice_of(view: "FrameworkView", current: dict[str, int]) -> SplitChoice:
    """The `SplitChoice` for ``view`` given the split in force.

    ``steps`` is left empty here: nothing in the build view carries a
    slot's step sizes yet (the offers that advertise them arrive with the
    enumeration rewrite), and the rule `parse` enforces does not read them.
    """
    return SplitChoice(
        framework_id=view.framework_id,
        reserve=int(view.reserve_or_pool or 0),
        slots=tuple(
            SlotTerms(s.slot_id, s.name, bool(s.variable),
                      int(s.active_points or 0), ())
            for s in view.slots),
        current=dict(current),
    )


def split_of_action(action_id: str, kind_prefix: str) -> tuple[str, str]:
    """``(framework_id, tail)`` of a completed split id
    ``<kind_prefix>:<framework_id>:split=<tail>``; ``("", "")`` for anything
    else (the legacy ``reallocate_slots:<fw>:<a,b>`` among it)."""
    base, sep, tail = (action_id or "").rpartition("=")
    parts = base.split(":")
    if (not sep or len(parts) != 3 or parts[0] != kind_prefix
            or not parts[1] or parts[2] != SPLIT_SUFFIX):
        return "", ""
    return parts[1], tail
