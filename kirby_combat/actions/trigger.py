"""Trigger — a stored action that fires when a condition matches a CombatEvent.

Per 6E1 p366-368 §Trigger. A Trigger is purchased as a Power Advantage; the
combatant pre-arranges an action (e.g., a held Energy Blast) that resolves
automatically when the trigger condition is satisfied by an in-game event.

This module models the trigger metadata + condition matcher + the
fire/recharge bookkeeping. It does NOT itself dispatch the stored action —
the caller (typically the session loop) calls `check_triggers(session,
event)` after each apply_event to discover which triggers matched and
should be fired.

Triggers are session-scoped state, kept in the (mutable) session.triggers
list. Charges, rechargeable flag, and per-trigger fire counts live there.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import CombatEvent


# ---------------------------------------------------------------------------
# Trigger model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TriggerCondition:
    """Predicate matching a CombatEvent.

    `event_type` matches the event's `kind`. `matches` is a dict of
    field-name → expected-value pairs; ALL must match for the condition to
    fire. Unknown event fields are treated as non-matches.
    """
    event_type: str
    matches: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trigger:
    """A stored action attached to a combatant.

    Mutable: charges decrement on fire; recharge flag controls whether the
    charge resets at trigger-defined intervals (caller responsibility).
    """
    id: str
    owner_id: str                              # combatant who owns this trigger
    condition: TriggerCondition
    action_template: dict[str, Any]            # parameters to instantiate the action
    charges: int | None = None                 # None = unlimited
    rechargeable: bool = False
    fires_count: int = 0


# ---------------------------------------------------------------------------
# Predicate evaluation
# ---------------------------------------------------------------------------

def _event_matches(event: CombatEvent, condition: TriggerCondition) -> bool:
    """True if the event satisfies the trigger condition.

    Match algorithm:
      1. event.kind == condition.event_type
      2. For each (field, expected) in condition.matches: getattr(event, field)
         must equal expected. Missing attribute → no match.
    """
    if getattr(event, "kind", None) != condition.event_type:
        return False
    for field_name, expected in condition.matches.items():
        actual = getattr(event, field_name, _MISSING)
        if actual is _MISSING:
            return False
        if actual != expected:
            return False
    return True


_MISSING = object()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TriggerFiring:
    """Record that a trigger matched and decremented its charges."""
    trigger_id: str
    owner_id: str
    matched_event_id: str
    action_template: dict[str, Any]


def check_triggers(
    triggers: list[Trigger],
    just_applied_event: CombatEvent,
) -> tuple[list[Trigger], list[TriggerFiring]]:
    """Return (new_triggers, firings) for triggers that match `just_applied_event`.

    Triggers with charges == 0 (depleted, non-rechargeable) are skipped.
    Each match decrements charges (if not None) and increments fires_count.
    Multiple triggers with the same condition all fire on the same event.

    The caller is responsible for converting `firings` into actual
    ActionDeclared/ActionResolved events using the action_template.
    """
    firings: list[TriggerFiring] = []
    new_triggers: list[Trigger] = []
    for t in triggers:
        if t.charges is not None and t.charges <= 0:
            new_triggers.append(t)
            continue
        if not _event_matches(just_applied_event, t.condition):
            new_triggers.append(t)
            continue

        firings.append(TriggerFiring(
            trigger_id=t.id,
            owner_id=t.owner_id,
            matched_event_id=getattr(just_applied_event, "id", ""),
            action_template=dict(t.action_template),
        ))
        new_charges = t.charges - 1 if t.charges is not None else None
        new_triggers.append(replace(t, charges=new_charges, fires_count=t.fires_count + 1))
    return new_triggers, firings


def recharge_trigger(triggers: list[Trigger], trigger_id: str) -> list[Trigger]:
    """Reset a rechargeable trigger's charges to its original count.

    This is a separate explicit step rather than automatic, because the
    "reset condition" is a campaign-level decision (per turn / per combat
    / etc.) — the engine doesn't presume.

    Looks up the trigger by id and, if rechargeable, restores `charges` to
    `fires_count + charges` (i.e., total observed = full count) so that the
    next check_triggers can fire it again. Caller may instead replace the
    trigger entirely if it wants exact original-charge semantics.

    Raises ValueError if the trigger isn't found or isn't rechargeable.
    """
    out: list[Trigger] = []
    found = False
    for t in triggers:
        if t.id != trigger_id:
            out.append(t)
            continue
        found = True
        if not t.rechargeable:
            raise ValueError(f"trigger {trigger_id!r} is not rechargeable")
        # Restore charges to fires_count + remaining charges = original
        original = (t.charges or 0) + t.fires_count
        out.append(replace(t, charges=original, fires_count=0))
    if not found:
        raise ValueError(f"trigger {trigger_id!r} not found")
    return out
