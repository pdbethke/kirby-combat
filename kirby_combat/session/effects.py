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
`session/apply.py` — that branch is still where these events are appended
to the log unchanged, but the canonical query helpers live here.
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
    every live instance (`adjustment_instances`). A SUMMARY for readers that
    want one line per stat (the Brief); the fade works per instance."""
    target_id: str
    stat: str
    net_delta: int
    fade_rate_per_turn: int


@dataclass(frozen=True)
class AdjustmentInstance:
    """One Adjustment on one stat, tracked on its own (6E1 p.139: "each one
    affects a character separately for purposes of determining when the
    character recovers lost points - they don't all lump together ... track
    each use of Drain separately", and "You should also apply this rule to
    positive Adjustment Powers").

    ``id`` is the `AdjustmentApplied` that started it. ``turn_ends`` counts
    the Post-Segment 12s that have passed since it landed (a
    `SegmentAdvanced` out of Segment 12), which is what a Delayed Return
    Rate's interval is counted in.
    """
    id: str
    target_id: str
    stat: str
    character_points: int
    fade_rate_per_turn: int
    fade_interval_turns: int
    cost_per_point: float
    turn_ends: int


def adjustment_instances(session: "CombatSession", combatant_id: str) -> list[AdjustmentInstance]:
    """Every Adjustment on this combatant, one per `AdjustmentApplied`, with
    what is left of it, oldest first. Spent ones (0 left) are dropped.

    `AdjustmentFaded` SETS one instance's remaining Character Points (the
    absolute-value discipline). A row written before instances were tracked
    names no ``adjustment_id``: it set the whole stat's total, and is read
    that way --- the stat's earlier instances to 0 and its latest to the
    total --- so an old log replays to the numbers it ran with.
    """
    records: dict[str, dict] = {}
    for evt in session.event_log:
        kind = getattr(evt, "kind", None)
        if kind == "SegmentAdvanced" and getattr(evt, "from_segment", None) == 12:
            for r in records.values():
                r["turn_ends"] += 1
            continue
        if getattr(evt, "target_id", None) != combatant_id:
            continue
        if kind == "AdjustmentApplied":
            interval = int(getattr(evt, "fade_interval_turns", 1))
            if interval < 1:
                raise ValueError(
                    f"AdjustmentApplied {evt.id!r} fades every {interval} Turns; "
                    "an interval is at least 1")
            records[evt.id] = {
                "stat": evt.stat, "cp": int(evt.delta or 0),
                "rate": int(getattr(evt, "fade_rate_per_turn", 5)),
                "interval": interval,
                "cpp": float(getattr(evt, "cost_per_point", 0) or 0),
                "turn_ends": 0,
            }
        elif kind == "AdjustmentFaded":
            which = getattr(evt, "adjustment_id", "") or ""
            if which:
                if which in records:
                    records[which]["cp"] = int(evt.remaining_delta)
                continue
            same = [r for r in records.values() if r["stat"] == evt.stat]
            for r in same:
                r["cp"] = 0
            if same:
                same[-1]["cp"] = int(evt.remaining_delta)
    return [
        AdjustmentInstance(
            id=i, target_id=combatant_id, stat=r["stat"], character_points=r["cp"],
            fade_rate_per_turn=r["rate"], fade_interval_turns=r["interval"],
            cost_per_point=r["cpp"], turn_ends=r["turn_ends"],
        )
        for i, r in records.items() if r["cp"] != 0
    ]


def adjustment_delta(session: "CombatSession", combatant_id: str, stat: str) -> int:
    """Net delta on one stat: the sum of its live instances."""
    return sum(i.character_points for i in adjustment_instances(session, combatant_id)
               if i.stat == stat)


def adjustments_for(session: "CombatSession", combatant_id: str) -> list[AdjustmentEffect]:
    """One `AdjustmentEffect` per stat, summed over its instances."""
    by_stat: dict[str, list[AdjustmentInstance]] = {}
    for inst in adjustment_instances(session, combatant_id):
        by_stat.setdefault(inst.stat, []).append(inst)
    out = []
    for stat, insts in by_stat.items():
        net = sum(i.character_points for i in insts)
        if net:
            out.append(AdjustmentEffect(target_id=combatant_id, stat=stat,
                                        net_delta=net,
                                        fade_rate_per_turn=insts[-1].fade_rate_per_turn))
    return out


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
    """Walk the log accumulating EntangleApplied / EntangleEscape pairs.

    The PHYSICAL Entangle: a Mental Paralysis is a separate Entangle that
    never adds to this one (6E1 p.219) --- see `Entangle.held`.
    """
    body: int | None = None
    pd = 0
    ed = 0
    for evt in session.event_log:
        kind = getattr(evt, "kind", None)
        target = getattr(evt, "target_id", None)
        if target != combatant_id:
            continue
        if getattr(evt, "mental_paralysis", False):
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

    A FlashApplied on a Sense Group already Flashed changes NOTHING. 6E1
    p.228: "If a character's affected by a Flash, generally he can't suffer
    any further effect from other Flashes of the same Sense Group ... until
    the first Flash wears off." This fold used to ADD the second Flash's
    Segments (citing "6E2 §Flash", which says no such thing) while
    ``Flash.is_flashed`` overwrote with them: two folds, two answers, neither
    the book's. ``Flash.apply`` no longer emits one, and this fold agrees
    with the rule for a log that has one. FlashRecovered sets the explicit
    remaining count for that sense group.
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
            if segments.get(sg, 0) <= 0:
                segments[sg] = seg
        elif kind == "FlashRecovered":
            sg = getattr(evt, "sense_group", "")
            segments[sg] = int(getattr(evt, "segments_remaining", 0))
    # Drop fully-recovered groups
    return FlashState(
        target_id=combatant_id,
        segments_by_sense={g: n for g, n in segments.items() if n > 0},
    )


# ---------------------------------------------------------------------------
# Presence Attack bookkeeping
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PresenceState:
    """A target's live Presence-Attack effect, folded from the log.

    ``tier`` is None and ``segments_remaining`` 0 when nothing is active --
    so a caller that always reads this gets today's behaviour for anyone who
    was never shouted at.
    """
    target_id: str
    tier: str | None = None
    segments_remaining: int = 0
    yields_to_id: str | None = None
    #: Whether the single Full Phase this result costs has been spent.
    #: The tier's own duration is `segments_remaining` and governs the DCV
    #: penalty; this governs the lost action, which 6E2 p.139 makes one
    #: Phase and not the whole five minutes.
    action_lost: bool = False

    @property
    def is_active(self) -> bool:
        return self.tier is not None and self.segments_remaining > 0


def presence_state(session: "CombatSession", combatant_id: str) -> PresenceState:
    """Walk the log accumulating PresenceApplied / PresenceFaded.

    Same shape as ``flash_state`` and ``entangle_state`` above, and for the
    same reason: ``PresenceFaded.segments_remaining`` states the RESULTING
    value rather than a delta, so this fold runs forward and never has to
    invert anything.

    A stronger tier replaces a weaker one and resets its clock; an equal tier
    refreshes the clock; a weaker one is ignored entirely -- 6E2 p.139's
    tiers are a ladder, and a shout must not un-cow someone already cowed.
    """
    from kirby_combat.pre_attacks.presence_effects import effect_for_tier

    tier: str | None = None
    remaining = 0
    yields_to: str | None = None
    action_lost = False
    for evt in session.event_log:
        kind = getattr(evt, "kind", None)
        if getattr(evt, "target_id", None) != combatant_id:
            continue
        if kind == "PresenceApplied":
            new_tier = getattr(evt, "tier", "") or ""
            new_rule = effect_for_tier(new_tier)
            if new_rule is None:
                continue
            current_rule = effect_for_tier(tier or "")
            current_rank = current_rule.rank if (current_rule and remaining > 0) else 0
            if new_rule.rank < current_rank:
                continue                       # a weaker shout changes nothing
            tier = new_tier
            action_lost = False            # a fresh shout costs a fresh Phase
            remaining = int(getattr(evt, "segments", 0) or 0)
            yields_to = (getattr(evt, "attacker_id", None) or None
                         if new_rule.yields else None)
        elif kind == "PresenceActionLost":
            action_lost = True
        elif kind == "PresenceFaded":
            remaining = max(0, int(getattr(evt, "segments_remaining", 0) or 0))
            if remaining == 0:
                tier = None
                yields_to = None
    if remaining <= 0:
        return PresenceState(target_id=combatant_id)
    return PresenceState(
        target_id=combatant_id, tier=tier,
        segments_remaining=remaining, yields_to_id=yields_to,
        action_lost=action_lost,
    )
