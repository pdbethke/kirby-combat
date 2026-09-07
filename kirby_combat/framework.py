"""Framework state — which Multipower slots are active, folded from the log.

`enumerate_actions` takes `slot_allocation` as a PARAMETER: the active set
has always been the caller's to hold, because no combatant in this engine
has a field for it. That is a reasonable split --- a framework's reserve is
build data --- but it left the caller tracking something the fight changes,
with nothing to read it back from.

`active_slots` closes that: a `reallocate` records the new set on the log,
and this folds the latest one forward per framework. The caller still owns
the reserve and the slot costs; what it no longer has to remember on its
own is which slots the fight has switched on.
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
