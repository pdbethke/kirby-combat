"""Persistent-effect bookkeeping derived from the combat event log.

Centralizes the per-target effect state carried by Adjustment, Entangle, and
Flash events. The functions below are pure derivations over `session.event_log`
— no Combatant fields are mutated directly. This keeps rewind cheap
(replay events to reconstruct state) and lets the action modules
(`actions/entangle.py`, `actions/flash.py`, `resolution/adjustments.py`) stay
thin.

Each helper takes a CombatSession and a combatant_id and walks the log
chronologically. They are intentionally conservative: an unknown event kind
is ignored.

This module also extends `apply_event` indirectly via the events branch in
`session/apply.py` — the Task 5 "no-op stub" branch is still where these
events are appended to the log, but the canonical query helpers live here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


# ---------------------------------------------------------------------------
# Adjustment fade bookkeeping
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AdjustmentEffect:
    """Net adjustment delta on a single (target, stat) pair, summed across
    all AdjustmentApplied events minus any AdjustmentFaded reversions."""
    target_id: str
    stat: str
    net_delta: int
    fade_rate_per_turn: int


def adjustment_delta(session: "CombatSession", combatant_id: str, stat: str) -> int:
    """Net delta on one stat after summing AdjustmentApplied / AdjustmentFaded.

    AdjustmentApplied contributes +delta. AdjustmentFaded sets the
    *remaining* delta (replaces the running sum) per its remaining_delta field.

    A combatant can have multiple unfaded applications on the same stat; their
    deltas sum. When AdjustmentFaded fires, it asserts the new running total.
    """
    running = 0
    for evt in session.event_log:
        kind = getattr(evt, "kind", None)
        target = getattr(evt, "target_id", None)
        if target != combatant_id:
            continue
        if kind == "AdjustmentApplied" and getattr(evt, "stat", None) == stat:
            running += int(getattr(evt, "delta", 0) or 0)
        elif kind == "AdjustmentFaded" and getattr(evt, "stat", None) == stat:
            running = int(getattr(evt, "remaining_delta", 0) or 0)
    return running


def adjustments_for(session: "CombatSession", combatant_id: str) -> list[AdjustmentEffect]:
    """List of net AdjustmentEffect entries for combatant_id (one per stat)."""
    by_stat: dict[str, dict] = {}
    for evt in session.event_log:
        kind = getattr(evt, "kind", None)
        target = getattr(evt, "target_id", None)
        if target != combatant_id:
            continue
        if kind == "AdjustmentApplied":
            stat = getattr(evt, "stat", "")
            entry = by_stat.setdefault(
                stat, {"delta": 0, "fade_rate": int(getattr(evt, "fade_rate_per_turn", 5))}
            )
            entry["delta"] += int(getattr(evt, "delta", 0) or 0)
            entry["fade_rate"] = int(getattr(evt, "fade_rate_per_turn", 5))
        elif kind == "AdjustmentFaded":
            stat = getattr(evt, "stat", "")
            entry = by_stat.setdefault(stat, {"delta": 0, "fade_rate": 5})
            entry["delta"] = int(getattr(evt, "remaining_delta", 0) or 0)
    return [
        AdjustmentEffect(
            target_id=combatant_id,
            stat=stat,
            net_delta=v["delta"],
            fade_rate_per_turn=v["fade_rate"],
        )
        for stat, v in by_stat.items()
        if v["delta"] != 0
    ]


# ---------------------------------------------------------------------------
# Entangle bookkeeping
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EntangleState:
    """Snapshot of a target's entangle state at the current point in the log."""
    target_id: str
    body_remaining: int
    entangle_pd: int
    entangle_ed: int
    is_entangled: bool


def entangle_state(session: "CombatSession", combatant_id: str) -> EntangleState:
    """Walk the log accumulating EntangleApplied / EntangleEscape pairs."""
    body: int | None = None
    pd = 0
    ed = 0
    for evt in session.event_log:
        kind = getattr(evt, "kind", None)
        target = getattr(evt, "target_id", None)
        if target != combatant_id:
            continue
        if kind == "EntangleApplied":
            body = int(getattr(evt, "entangle_body", 0))
            pd = int(getattr(evt, "entangle_pd", 0))
            ed = int(getattr(evt, "entangle_ed", 0))
        elif kind == "EntangleEscape":
            if body is None:
                continue
            if getattr(evt, "escaped", False):
                body = None
            else:
                body = max(0, body - int(getattr(evt, "damage_to_entangle_body", 0)))
                if body == 0:
                    body = None
    return EntangleState(
        target_id=combatant_id,
        body_remaining=body or 0,
        entangle_pd=pd,
        entangle_ed=ed,
        is_entangled=body is not None and body > 0,
    )


# ---------------------------------------------------------------------------
# Flash bookkeeping
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FlashState:
    """Per-sense-group flash segments remaining for a target."""
    target_id: str
    segments_by_sense: dict[str, int] = field(default_factory=dict)

    @property
    def is_flashed(self) -> bool:
        return any(n > 0 for n in self.segments_by_sense.values())


def flash_state(session: "CombatSession", combatant_id: str) -> FlashState:
    """Walk the log accumulating FlashApplied / FlashRecovered events.

    FlashApplied with the same sense_group as an existing entry STACKS
    (per 6E2 §Flash — concurrent flashes accumulate segments). FlashRecovered
    sets the explicit remaining count for that sense group.
    """
    segments: dict[str, int] = {}
    for evt in session.event_log:
        kind = getattr(evt, "kind", None)
        target = getattr(evt, "target_id", None)
        if target != combatant_id:
            continue
        if kind == "FlashApplied":
            sg = getattr(evt, "sense_group", "")
            seg = int(getattr(evt, "segments", 0))
            segments[sg] = segments.get(sg, 0) + seg
        elif kind == "FlashRecovered":
            sg = getattr(evt, "sense_group", "")
            segments[sg] = int(getattr(evt, "segments_remaining", 0))
    # Drop fully-recovered groups
    return FlashState(
        target_id=combatant_id,
        segments_by_sense={g: n for g, n in segments.items() if n > 0},
    )
