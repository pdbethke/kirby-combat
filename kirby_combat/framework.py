"""Framework state — which Multipower slots are active, folded from the log.

`enumerate_actions` takes `slot_allocation` as a PARAMETER: the active set
has always been the caller's to hold, because no combatant in this engine
has a field for it. That is a reasonable split --- a framework's reserve is
build data --- but it left the caller tracking something the fight changes,
with nothing to read it back from.

`slot_points_for` closes that: a `SlotsAllocated` is folded onto the
combatant (`CombatantState.slot_points`) and this reads it back.

`allocation_for` goes the rest of the way. The reserve and the per-slot
costs were never really the caller's either --- they are build data, and
`HeroCombatant.framework_view()` has always exposed them --- so it assembles
the whole `slot_allocation` mapping `enumerate_actions` wants, from the
build plus the log. A caller may still pass its own; what it no longer has
to do is keep one in step with a fight it is not otherwise tracking.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

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


def slot_points_for(actor, framework_id: str) -> dict[str, int] | None:
    """The points ``actor`` has put in each slot of ``framework_id``, as the
    latest `SlotsAllocated` left them on his state (6E1 p.404-406), or None
    when the framework has not been opened.

    None means the build reads as written. That state exists only during
    setup: the opening is part of starting a fight, and a Segment is
    refused without it. There is deliberately no default split here ---
    a default would be one build's choice imposed on every other.

    Takes the combatant, not the session: the split is folded onto him
    (`apply_event`), so reading it needs no log scan.
    """
    if actor is None:
        return None
    split = actor.state.slot_points.get(framework_id)
    return None if split is None else dict(split)


class Allocation(NamedTuple):
    """One framework's allocation, as `enumerate_actions` and the upkeep
    readers see it. Indexes 0-3 keep the order the old 4-tuple had."""

    reserve: int
    #: Points drawn: the sum of the split.
    used: int
    #: Slots holding points (> 0): the ones that are on (6E1 p.402).
    active: set
    #: Full Active Points of each slot --- build data.
    slot_costs: dict
    #: The split itself, slot id -> points.
    points: dict


def allocation_for(session: "CombatSession", actor) -> dict[str, Allocation] | None:
    """The `slot_allocation` mapping `enumerate_actions` wants, assembled.

    ``framework_id -> Allocation`` for every framework the actor has
    OPENED: the reserve and per-slot costs from the BUILD
    (`framework_view()`), the points from his folded state
    (`slot_points_for`). A framework not yet opened has no entry, which
    every reader takes as "the build as written".

    ``session`` is accepted for the callers' sake and no longer read: the
    split is on the combatant, not scanned out of the log.

    Returns ``None`` when the actor has no frameworks, which
    `enumerate_actions` reads as "no gate".
    """
    views = list(getattr(actor, "framework_view", lambda: [])() or [])
    if not views:
        return None

    allocation: dict[str, Allocation] = {}
    for view in views:
        points = slot_points_for(actor, view.framework_id)
        if points is None:
            continue
        allocation[view.framework_id] = Allocation(
            reserve=int(view.reserve_or_pool or 0),
            used=sum(points.values()),
            active={sid for sid, pts in points.items() if pts > 0},
            slot_costs={s.slot_id: int(s.active_points or 0) for s in view.slots},
            points=points,
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


#: A points field is ASCII digits only (int() would also take spaces,
#: underscores and non-ASCII digits); the minus is kept so a negative
#: reaches the rule check and is refused there with its reason.
_POINTS = re.compile(r"-?[0-9]+")


@dataclass(frozen=True)
class SlotTerms:
    """What a split needs to know about one slot (6E1 p.404-406).

    ``max_points`` is the slot's Active Points; ``steps`` the points of
    each rung of its priced ladder (the points themselves need not sit on a
    rung: p.406), or None for a slot read from a plain, unpriced view. A
    variable slot whose ladder is just ``(0, max_points)`` has nothing
    between off and as bought, so a share in between is refused (R9); a
    variable slot with no ladder at all cannot be checked, and
    `_check_split` raises ``TypeError`` rather than check half the rule.
    """

    slot_id: str
    name: str
    variable: bool
    max_points: int
    steps: tuple[int, ...] | None


def _check_split(
    framework_id: str, reserve: int, terms: dict[str, SlotTerms],
    points: dict[str, int],
) -> int:
    """The one rule set a split is held to; returns the points drawn.

    6E1 p.404-405: a FIXED slot is on at its full Active Points or off. A
    VARIABLE slot takes any share of the reserve from 0 to its Active
    Points (p.405). p.404: the shares together may not exceed the reserve.
    Raises ``KeyError`` for a slot the framework lacks, ``ValueError`` for
    a share the slot's kind forbids, ``ReserveExceeded`` for an overdraw,
    and ``TypeError`` for a variable slot with no priced ladder (an unpriced
    view, which is the caller's mistake, not the seat's).
    """
    unknown = sorted(sid for sid in points if sid not in terms)
    if unknown:
        raise KeyError(f"framework {framework_id!r} has no slot(s) {unknown}")
    for sid, pts in points.items():
        t = terms[sid]
        if t.variable:
            if t.steps is None:
                # Not a rule break but a caller's mistake: an unpriced view
                # cannot say whether a share is legal (R9), so nothing is
                # checked against it rather than half of it.
                raise TypeError(
                    f"{t.name!r} is a variable slot with no priced ladder; "
                    f"check a split against `priced_framework_view()`")
            if not 0 <= pts <= t.max_points:
                raise ValueError(
                    f"{t.name!r} is a variable slot of {t.max_points} Active "
                    f"Points; {pts} is outside 0..{t.max_points} (6E1 p.405)")
            if (t.steps is not None and tuple(t.steps) == (0, t.max_points)
                    and 0 < pts < t.max_points):
                raise ValueError(
                    f"{t.name!r} cannot be split: it has no step between off "
                    f"and its full {t.max_points} Active Points, so it takes "
                    f"0 or {t.max_points}, not {pts} (6E1 p.404-406)")
        elif pts not in (0, t.max_points):
            raise ValueError(
                f"{t.name!r} is a fixed slot: it is off (0) or on at its "
                f"full {t.max_points} Active Points, not {pts} (6E1 p.404-405)")
    drawn = sum(points.values())
    if drawn > reserve:
        raise ReserveExceeded(framework_id, drawn, reserve)
    return drawn


def _terms_of(slot) -> SlotTerms:
    """A slot's `SlotTerms`: its ladder when the view is priced
    (`PricedSlotView`), None for a plain `SlotView`."""
    from kirby_combat.models import PricedSlotView

    return SlotTerms(
        slot.slot_id, slot.name, bool(slot.variable),
        int(slot.active_points or 0),
        tuple(st.points for st in slot.steps)
        if isinstance(slot, PricedSlotView) else None)


def validate_split(view: "FrameworkView", points: dict[str, int]) -> int:
    """Check a proposed split of ``view``'s reserve; returns the total drawn.

    6E1 p.404-406 (rules in `_check_split`); p.406: points need not sit on
    a step. ENFORCED, NOT ASSUMED: an offer is not a permission slip, so
    the resolver re-asks this of whatever id it is handed.
    """
    terms = {s.slot_id: _terms_of(s) for s in view.slots}
    return _check_split(view.framework_id, int(view.reserve_or_pool or 0),
                        terms, points)


@dataclass(frozen=True)
class Preset:
    """A named split the menu suggests (spec §5.3): the full split, every
    slot named (0 = off), and what it buys in words.

    ``standing`` marks the player's own (`StandingSplit`, spec §5.5a), which
    come first; ``standard`` marks the one he fights with by default, which
    only the opening reads. The neutral ones ("All in <slot>", "Even",
    "<fixed slot> + remainder") read nothing but the framework: no board,
    no threat, no enemy.
    """

    name: str
    points: dict[str, int]
    effect_text: str
    standing: bool
    standard: bool


@dataclass(frozen=True)
class StandingSplit:
    """A split the player has named and saved for a Multipower (spec §5.5a):
    "Patrol", "Combat". kirby-api stores and validates them on save and
    hands them over at seating as plain data; the engine re-checks each
    against the build in play (`validate_split`) and leaves one that no
    longer fits off the menu, with its reason in the brief.

    ``points`` need not name every slot (an unnamed slot is off);
    ``position`` orders them; ``standard`` marks his usual combat set.
    """

    name: str
    points: dict[str, int]
    standard: bool
    position: int


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
    with it changes nothing and is refused. ``presets`` are the menu's
    suggestions (`split_menu.presets_for`), each one an answer; any other
    legal split is one too.
    """

    framework_id: str
    reserve: int
    slots: tuple[SlotTerms, ...]
    current: dict[str, int]
    presets: tuple[Preset, ...]

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
        # The empty WHOLE tail means every slot off; an empty TERM is a typo.
        for term in (tail.split(SPLIT_JOIN) if tail else ()):
            sid, at, raw = term.partition(SPLIT_AT)
            if not (sid and at and _POINTS.fullmatch(raw)):
                raise ValueError(f"{term!r} is not <slot>{SPLIT_AT}<integer points>")
            pts = int(raw)
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


def split_choice_of(view: "FrameworkView", current: dict[str, int],
                    presets: tuple[Preset, ...]) -> SplitChoice:
    """The `SplitChoice` for ``view`` given the split in force.

    Pass the PRICED view (`HeroCombatant.priced_framework_view`): each
    slot's ladder rides in its `SlotTerms.steps`, so `parse` can refuse a
    share of a slot that has no step between off and as bought. A plain
    view carries no ladders, and `parse` raises ``TypeError`` on its
    variable slots rather than skip that rule.
    """
    return SplitChoice(
        framework_id=view.framework_id,
        reserve=int(view.reserve_or_pool or 0),
        slots=tuple(_terms_of(s) for s in view.slots),
        current=dict(current),
        presets=tuple(presets),
    )


def split_of_action(action_id: str, kind_prefix: str) -> tuple[str, str]:
    """``(framework_id, tail)`` of a completed split id
    ``<kind_prefix>:<framework_id>:split=<tail>``; ``("", "")`` for anything
    else."""
    base, sep, tail = (action_id or "").rpartition("=")
    parts = base.split(":")
    if (not sep or len(parts) != 3 or parts[0] != kind_prefix
            or not parts[1] or parts[2] != SPLIT_SUFFIX):
        return "", ""
    return parts[1], tail
