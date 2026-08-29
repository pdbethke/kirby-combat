"""What a landed Presence Attack COSTS the target — 6E2 p.138-139.

``presence.py`` next door resolves the roll and names the tier. It has always
stopped there, and said so: ``can_act_after``'s docstring reads *"RAW is
stricter -- at 'awed' (PRE+20) the target 'will not act for 1 Full Phase'
(6E2 p139) -- but consuming the table's mechanical consequences is separate
work from correcting the table."* This module is that work. Until it existed,
a Presence Attack changed nothing mechanically, and PRE was a Characteristic
you could pay Character Points for and never cash in.

**The tiers, in our own words** (this project ships no rules text; open your
own copy). Each threshold is the Presence Attack roll total against the
target's PRE:

===============  ==========================================================
at PRE           **impressed** — he hesitates enough that the attacker may
                 act before him that Phase. Effects last no more than 1 Turn.
at PRE +10       **very impressed** — hesitates as above AND performs only a
                 Half Phase Action during his next Phase. About 1 Minute.
at PRE +20       **awed** — will not act for 1 Full Phase, and is at half
                 DCV. About 5 Minutes.
at PRE +30       **cowed** — may surrender, run away or faint; 0 DCV.
                 About 20 Minutes.
at PRE +40       **overwhelmed** (GM's option) — the SAME combat effects as
                 PRE +30, with far severer effects on mind and personality.
                 About 1 Hour.
===============  ==========================================================

**Durations are derived, not chosen.** 6E2 p.18: a Turn is 12 seconds and 12
Segments, each 1 second. So 1 Turn = 12 segments, 1 Minute = 60, 5 Minutes =
300, 20 Minutes = 1200, 1 Hour = 3600. A scale that merely *preserves the
ordering* of the book's figures would be a house rule wearing a citation.

**State follows the house pattern and invents nothing.** Adjustment, Entangle
and Flash all work the same way (``session/effects.py``): an ``Applied`` event
carries the magnitude, a ``Faded`` event carries the **resulting remaining
value, absolute**, and a pure fold reads them forward. The absolute-remaining
contract is the load-bearing part — a delta would have to be inverted to read
state backwards, and this project has already proved inversion cannot be made
correct (END clamps at 0 on spend, destroying the amount really taken).

**The decrement is caller-driven**, like ``Flash.recover()`` and
``HeldAction.expire_for_combatant_next_phase()``. A driver advancing a Segment
calls ``tick_all``. Nothing here reads a clock: ``Encounter`` and ``Timeline``
still diverge (``encounter.py``'s own docstring measures it), so a remaining
COUNT is honest where an absolute "expires at segment N" would not be.

**Deliberately not modelled, and recorded rather than dropped silently:**

* the **+5 / +10 PRE bonus** a target gets for resisting *contrary* Presence
  Attacks at the impressed / very-impressed and awed tiers;
* the **EGO Roll to resist**, with its escalating −1 / −2 / −3 / −5 penalties.
  6E2 p.139 gates this on the GM ("if the GM permits the target a chance"),
  so it is a table ruling rather than a mechanic the engine can decide;
* the **Psychological Complication** framing of the cowed and overwhelmed
  tiers, which is character-sheet territory, not combat resolution.

The mental/roleplay consequences of each tier are likewise out of scope —
this module prices the COMBAT effects, which are the ones the book states in
numbers.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


#: 6E2 p.18 — a Turn is 12 seconds and 12 Segments, each 1 second.
SEGMENTS_PER_TURN = 12
_SEGMENTS_PER_MINUTE = 60


@dataclass(frozen=True)
class PresenceTier:
    """One row of 6E2 p.139's ladder, as mechanics."""

    #: The attacker may act before the target that Phase.
    yields: bool
    #: Only a Half Phase Action during the target's next Phase.
    half_phase: bool
    #: Will not act for 1 Full Phase.
    no_action: bool
    #: Folded through ``cv_modifiers.apply_cv_factor``, which accepts only
    #: 1.0, 0.5 and 0.0 -- the values 6E2 p.39 grounds. Every tier here uses
    #: one of those, so none can raise at resolution time.
    dcv_factor: float
    #: Derived from the book's wall-clock figure; see the module docstring.
    duration_segments: int
    #: Severity. A lower rank never overwrites a higher one.
    rank: int
    #: The page this row implements.
    citation: str


PRESENCE_TIERS: dict[str, PresenceTier] = {
    "impressed": PresenceTier(
        yields=True, half_phase=False, no_action=False, dcv_factor=1.0,
        duration_segments=SEGMENTS_PER_TURN, rank=1,
        citation="6E2 p.139, at PRE: hesitates so the attacker may act "
                 "first that Phase; no more than 1 Turn.",
    ),
    "very_impressed": PresenceTier(
        yields=True, half_phase=True, no_action=False, dcv_factor=1.0,
        duration_segments=_SEGMENTS_PER_MINUTE, rank=2,
        citation="6E2 p.139, at PRE+10: hesitates as above and takes only a "
                 "Half Phase Action next Phase; about 1 Minute.",
    ),
    "awed": PresenceTier(
        yields=False, half_phase=False, no_action=True, dcv_factor=0.5,
        duration_segments=5 * _SEGMENTS_PER_MINUTE, rank=3,
        citation="6E2 p.139, at PRE+20: will not act for 1 Full Phase and is "
                 "at half DCV; about 5 Minutes.",
    ),
    "cowed": PresenceTier(
        yields=False, half_phase=False, no_action=True, dcv_factor=0.0,
        duration_segments=20 * _SEGMENTS_PER_MINUTE, rank=4,
        citation="6E2 p.139, at PRE+30: may surrender, run away or faint; "
                 "0 DCV; about 20 Minutes.",
    ),
    "overwhelmed": PresenceTier(
        # Identical combat fields to `cowed` BY THE BOOK, not by oversight:
        # 6E2 p.139 says PRE+40 produces the same combat effects as PRE+30.
        # Only the duration and the (unmodelled) mental severity differ.
        yields=False, half_phase=False, no_action=True, dcv_factor=0.0,
        duration_segments=60 * _SEGMENTS_PER_MINUTE, rank=5,
        citation="6E2 p.139, at PRE+40 (GM's option): the same combat effects "
                 "as PRE+30 with far severer mental ones; about 1 Hour.",
    ),
}


def effect_for_tier(tier: str | None) -> PresenceTier | None:
    """The rules row for a tier, or ``None`` for ``"no_effect"``.

    ``None`` rather than a raise: ``presence_attack_effect`` legitimately
    returns ``"no_effect"`` for a roll under the target's PRE, and a shout
    that lands on nobody is an ordinary outcome, not an error.
    """
    return PRESENCE_TIERS.get(tier or "")


class PresenceEffects:
    """Applying and ageing a landed Presence Attack."""

    @staticmethod
    def apply(
        session: "CombatSession",
        *,
        target_id: str,
        attacker_id: str,
        tier: str,
    ) -> tuple["CombatSession", PresenceTier | None]:
        """Record a landed tier.

        Returns ``(session, None)`` unchanged when the roll produced
        ``no_effect`` or when a STRONGER tier already holds -- a shout must
        not un-cow someone already cowed. An equal tier refreshes the clock:
        the target is freshly cowed, not ignored.
        """
        from kirby_combat.session.apply import apply_event
        from kirby_combat.session.effects import presence_state
        from kirby_combat.session.events import PresenceApplied, make_author_combatant

        rule = effect_for_tier(tier)
        if rule is None:
            return session, None

        current = presence_state(session, target_id)
        current_rule = effect_for_tier(current.tier) if current.is_active else None
        if current_rule is not None and current_rule.rank > rule.rank:
            return session, None

        evt = PresenceApplied(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(attacker_id),
            target_id=target_id,
            attacker_id=attacker_id,
            tier=tier,
            segments=rule.duration_segments,
        )
        return apply_event(session, evt), rule

    @staticmethod
    def tick(
        session: "CombatSession", combatant_id: str, *, segments: int = 1,
    ) -> "CombatSession":
        """Age one combatant's effect by ``segments``, emitting the fade.

        A no-op (and no event) when nothing is active, so a driver may call
        it unconditionally for everyone.
        """
        from kirby_combat.session.apply import apply_event
        from kirby_combat.session.effects import presence_state
        from kirby_combat.session.events import PresenceFaded, make_author_engine

        state = presence_state(session, combatant_id)
        if not state.is_active:
            return session

        remaining = max(0, state.segments_remaining - max(0, int(segments)))
        evt = PresenceFaded(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_engine(),
            target_id=combatant_id,
            segments_remaining=remaining,
        )
        return apply_event(session, evt)

    @staticmethod
    def tick_all(
        session: "CombatSession", *, segments: int = 1,
    ) -> "CombatSession":
        """What a driver advancing a Segment calls. Order is the combatant
        map's, which is insertion order and therefore stable for replay."""
        s = session
        for combatant_id in list(session.combatants):
            s = PresenceEffects.tick(s, combatant_id, segments=segments)
        return s


def can_act(session: "CombatSession", combatant_id: str) -> bool:
    """False while a Presence Attack is holding this combatant frozen.

    The live-state counterpart to ``presence.can_act_after``, which answers
    the same question from a tier string alone. 6E2 p.139 stops the target
    outright from ``awed`` upward.
    """
    from kirby_combat.session.effects import presence_state

    state = presence_state(session, combatant_id)
    rule = effect_for_tier(state.tier) if state.is_active else None
    return not (rule is not None and rule.no_action)


def presence_cv_modifiers(
    session: "CombatSession", combatant_id: str,
) -> dict[str, float]:
    """This combatant's Presence contribution to the CV seam.

    Wired into ``cv_modifiers._CV_MODIFIER_SOURCES``. Opponent-independent --
    an awed character is at half DCV against everyone, not just whoever
    frightened him -- so it belongs in the original seam rather than the
    per-opponent one added for 6E2 p.9.
    """
    from kirby_combat.session.effects import presence_state

    state = presence_state(session, combatant_id)
    rule = effect_for_tier(state.tier) if state.is_active else None
    if rule is None or rule.dcv_factor == 1.0:
        return {}
    return {"dcv_factor": rule.dcv_factor}
