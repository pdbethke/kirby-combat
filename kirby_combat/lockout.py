"""Lockout: a framework slot that, while in use, shuts its siblings out.

6E1 p.388: "A power with this Limitation prevents the character from using
some or all of his other powers when it's in use. It's most commonly taken
for a slot in a Power Framework that prevents the character from using
other slots in the Framework (in situations where that normally wouldn't be
the case)."

`enumerate_actions` has taken `blocked_lockout_ids` since the kirby-api
driver's PR-96, and `run_phase` never passed it, so a Lockout limitation
bought points off a power and cost the character nothing. This module is the
fold that feeds it, from the fight's own log.

WHAT IS BLOCKED --- the driver's ruling, kept: the slots that share the
in-use Lockout slot's FRAMEWORK, and nothing else. A Lockout outside a
framework prevents whatever its own text names ("can't use this while using
Desolidification", 6E1 p.193), and nothing in a build says which powers that
is in a form an engine can read, so it blocks nothing rather than inventing
a set; the limitation text still reaches the chooser through the offer's
`[limited: ...]` label.

WHEN A SLOT IS "IN USE" --- an explicit ruling, because the page does not
define it beyond the Power's own duration:

- a CONTINUING EFFECT it established is still in force. 6E1 p.388's own
  example is a spell bought "Lockout (cannot cast this spell or other spells
  while maintaining Mind Control)": the Mind Control is in use for as long
  as it holds, and its siblings are shut out that whole time;
- an attack fired with it earlier in the SAME Segment (the driver's rule:
  the lock cleared at every Segment advance). An Instant Power is in use
  when it is used, and no longer.

NOT BUILT: an Entangle bought with Lockout "while the Entangle affects a
target" (6E1 p.388's Elastic Body Entrapment). Entangle is an Instant
Power, so it is in use only as it is used unless its own text extends it,
and `EntangleApplied` records no source power to hold the extension
against. Such a slot locks nothing beyond the Segment it fires in.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


def _lockout_ids(actor) -> frozenset[str]:
    """The source ids of this actor's powers bought with Lockout.

    From the attack views (which carry the flag, and survive a rebuild from
    a snapshot) AND from the build's own powers: a continuing Mental Power
    such as Mind Control is offered off the build, not off `attacks`, and is
    the commonest thing a Lockout is "maintaining" (6E1 p.388).
    """
    from kirby_combat.hero_view import _has_modifier

    ids = {
        str(a.source_id) for a in (getattr(actor, "attacks", None) or [])
        if getattr(a, "lockout", False) and getattr(a, "source_id", None)
    }
    stack = list(getattr(getattr(actor, "hero", None), "powers", None) or [])
    while stack:
        power = stack.pop()
        stack.extend(getattr(power, "sub_powers", None) or [])
        if getattr(power, "id", None) and _has_modifier(power, "LOCKOUT"):
            ids.add(str(power.id))
    return frozenset(ids)


def _fired_this_segment(session: "CombatSession", actor_id: str) -> set[str]:
    """Power ids this actor resolved an attack with since the last Segment
    advance. The clock is the log's own: a `SegmentAdvanced` resets it."""
    fired: set[str] = set()
    for evt in session.event_log:
        kind = getattr(evt, "kind", None)
        if kind == "SegmentAdvanced":
            fired.clear()
            continue
        if kind != "ActionResolved":
            continue
        author = getattr(evt, "author", None)
        if getattr(author, "id", None) != actor_id:
            continue
        payload = getattr(evt, "result_payload", None) or {}
        source = payload.get("power_source_id")
        if source:
            fired.add(str(source))
    return fired


def _maintained(session: "CombatSession", actor_id: str) -> set[str]:
    """Power ids behind a continuing effect this actor still holds."""
    from kirby_combat.mental.continuing import continuing_effects

    return {
        e.source_id for e in continuing_effects(session)
        if e.attacker_id == actor_id and e.source_id
    }


def in_use_lockout_ids(session: "CombatSession", actor) -> frozenset[str]:
    """This actor's Lockout powers that are in use right now."""
    lockouts = _lockout_ids(actor)
    if not lockouts:
        return frozenset()
    in_use = _fired_this_segment(session, actor.id) | _maintained(session, actor.id)
    return frozenset(lockouts & in_use)


def blocked_lockout_ids(session: "CombatSession", actor) -> frozenset[str]:
    """The slot ids an in-use Lockout slot shuts out: its framework siblings.

    The shape `enumerate_actions(blocked_lockout_ids=...)` wants --- the
    sibling set, NOT including the locked-to slot itself, which stays
    usable (6E1 p.388 prevents "his other powers").
    """
    in_use = in_use_lockout_ids(session, actor)
    if not in_use:
        return frozenset()
    blocked: set[str] = set()
    for framework in actor.framework_view() or []:
        slot_ids = {str(slot.slot_id) for slot in framework.slots}
        for locked in in_use & slot_ids:
            blocked |= slot_ids - {locked}
    return frozenset(blocked - in_use)
