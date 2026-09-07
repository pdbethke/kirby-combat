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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


def parse_reallocation(action_id: str) -> tuple[str, tuple[str, ...]]:
    """Read a framework id and its slot ids out of an offer's action_id.

    The two shapes enumeration writes::

        reallocate_slots:<framework_id>:<slot_id,slot_id,...>
        reconfigure_vpp:<framework_id>

    Returns ``("", ())`` for anything else, so a caller can refuse rather
    than act on a framework it could not identify.
    """
    parts = (action_id or "").split(":")
    if len(parts) < 2 or not parts[1]:
        return "", ()
    framework_id = parts[1]
    if len(parts) < 3 or not parts[2]:
        return framework_id, ()
    return framework_id, tuple(s for s in parts[2].split(",") if s)


def active_slots(
    session: "CombatSession", combatant_id: str, framework_id: str,
) -> tuple[str, ...]:
    """The slots this combatant has switched on for ``framework_id``.

    The LATEST reallocation wins --- each one states the whole active set
    rather than a change to it, which is the same absolute-value discipline
    `session/effects.py` requires of every other state-changing event. A
    delta would be unrecoverable the moment one was missed.

    Empty when the fight has not reallocated this framework, which means
    "no opinion", not "nothing active": the build's own default set is the
    caller's to supply.
    """
    latest: tuple[str, ...] = ()
    for evt in session.event_log:
        if getattr(evt, "kind", None) != "ActionResolved":
            continue
        payload = getattr(evt, "result_payload", None) or {}
        if (
            payload.get("kind") == "reallocate"
            and payload.get("combatant_id") == combatant_id
            and payload.get("framework_id") == framework_id
        ):
            latest = tuple(payload.get("active_slot_ids") or ())
    return latest


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
        # so the same accounting `validate_allocation` uses applies here --
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

    6E1 p.204: a Multipower's reserve is the total Active Points its slots
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


def validate_allocation(actor, framework_id: str, slot_ids) -> int:
    """Check a proposed active set against the framework's reserve.

    Returns the Active Points the set draws --- fixed slots at full cost,
    variable slots capped by whatever the reserve has left. Raises
    ``ReserveExceeded`` when the FIXED slots alone cannot fit, and
    ``KeyError`` when the framework or a slot is not on this actor's build.

    ENFORCED, NOT ASSUMED. `enumerate_actions` gates which slots it OFFERS
    against the remaining reserve, but an offer is not a permission slip:
    the reallocate action names its whole set in one id, and a chooser that
    returns a hand-built id would otherwise switch on a configuration the
    build cannot pay for. The reserve is the constraint the framework
    exists to impose, so the resolver checks it rather than trusting the
    menu.
    """
    views = {
        v.framework_id: v
        for v in (getattr(actor, "framework_view", lambda: [])() or [])
    }
    view = views.get(framework_id)
    if view is None:
        raise KeyError(f"no framework {framework_id!r} on {actor.id!r}")

    slots = {s.slot_id: s for s in view.slots}
    unknown = [s for s in slot_ids if s not in slots]
    if unknown:
        raise KeyError(
            f"framework {framework_id!r} has no slot(s) {sorted(unknown)}"
        )

    # FIXED vs VARIABLE, which is the whole shape of a Multipower.
    #
    # A FIXED slot is all-or-nothing: switch it on and it draws its full
    # Active Points from the reserve. That is what makes it cheap.
    #
    # A VARIABLE slot may be run at ANY portion of its Active Points --- it
    # costs more real points precisely for that flexibility --- so it can be
    # dialled down to whatever the reserve has left. Charging one its full
    # cost here would refuse configurations the book allows.
    #
    # So the constraint is on the FIXED slots: they must fit outright.
    # Variables then share whatever remains, and how they split it is the
    # character's choice at the moment of use, not a decision this function
    # makes for them.
    reserve = int(view.reserve_or_pool or 0)
    fixed = [sid for sid in slot_ids if not slots[sid].variable]
    fixed_draw = sum(int(slots[sid].active_points or 0) for sid in fixed)
    if fixed_draw > reserve:
        raise ReserveExceeded(framework_id, fixed_draw, reserve)

    # What the set draws in total: the fixed slots at full cost, plus each
    # variable capped by what is left. A variable slot with no room left
    # draws nothing, which is legal --- it is on, at zero.
    drawn = fixed_draw
    for sid in slot_ids:
        slot = slots[sid]
        if not slot.variable:
            continue
        drawn += min(int(slot.active_points or 0), max(0, reserve - drawn))
    return drawn
