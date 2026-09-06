"""Turning a chosen ``LegalAction`` into a resolved one.

THE GAP THIS MAKES COUNTABLE. Measured 2026-09-06: ``enumerate_actions``
can offer **52** kinds of action, and the engine could execute **none** of
them from that menu. The rules largely exist --- some thirty modules under
``kirby_combat/actions/`` --- but nothing mapped a chosen action onto them.
That mapping lived in the parked kirby-api driver as 39 ``_resolve_*``
methods behind a 1,070-line dispatcher, tangled with the database.

This registry is the engine's half of that mapping, and it is deliberately
small and honest rather than a stub of all 52:

``resolve_chosen`` dispatches on ``LegalAction.kind``. A kind with no
registered resolver raises ``UnresolvableAction`` naming it.

**THE RAISE IS THE DESIGN.** A registry that silently skipped unknown kinds
would turn a 46-kind gap into a fight that quietly does nothing on half its
Phases --- precisely the class of failure this carve-out exists to end, and
the same shape as the bug where every AOE/TRIGGER modifier was silently
inert because a name never matched. Raising makes the gap a number:
``registered_kinds()`` is asserted by a test, so each migration out of
kirby-api moves it, and no migration has to touch the loop.

The loop offers ``on_unresolvable="raise" | "skip"`` for callers who want a
long fight to make progress while the registry fills. A skip is always
recorded on the Phase result --- never invisible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from kirby_combat.actions.recording import (
    resolve_attack_in_session, resolve_mental_blast_in_session,
)
from kirby_combat.enumeration import LegalAction

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate


class UnresolvableAction(Exception):
    """A chosen action's ``kind`` has no registered resolver.

    Carries the kind so a caller can report exactly which rule is still
    outside the engine, rather than "something went wrong in a Phase".
    """

    def __init__(self, kind: str, action_id: str = "") -> None:
        self.kind = kind
        self.action_id = action_id
        known = ", ".join(sorted(registered_kinds()))
        super().__init__(
            f"no resolver registered for action kind {kind!r}"
            + (f" (action {action_id!r})" if action_id else "")
            + f"; the engine can currently resolve: {known}"
        )


@dataclass
class ResolvedAction:
    """What one resolved Phase produced.

    ``events`` is the slice of the session's log this resolution appended,
    which is what a networked consumer extrudes: it persists and broadcasts
    these, and owns no rule about what they mean.
    """

    session: "CombatSession"
    kind: str
    action_id: str
    result: Any = None
    events: list[Any] = field(default_factory=list)


#: kind -> resolver. Populated by ``@resolves`` at import time.
_RESOLVERS: dict[str, Callable[..., ResolvedAction]] = {}


def resolves(*kinds: str):
    """Register a resolver for one or more ``LegalAction.kind`` values."""

    def decorate(fn: Callable[..., ResolvedAction]):
        for kind in kinds:
            if kind in _RESOLVERS:
                raise ValueError(f"resolver for {kind!r} already registered")
            _RESOLVERS[kind] = fn
        return fn

    return decorate


def registered_kinds() -> frozenset[str]:
    """Every kind the engine can resolve today.

    Asserted by a test on purpose --- see the module docstring. This number
    growing is the measure of the carve-out's progress.
    """
    return frozenset(_RESOLVERS)


def _events_since(before: "CombatSession", after: "CombatSession") -> list[Any]:
    return list(after.event_log[len(before.event_log):])


@resolves("attack", "strike")
def _resolve_attack(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """A ranged or hand-to-hand attack against one target.

    The attack power comes off ``LegalAction._attack_view``, the engine-side
    handle enumeration attached when it built the offer. That handle, rather
    than a re-lookup by xmlid or name, is what keeps the right power: a
    character can hold several powers of the same xmlid, and matching on
    ``xmlid + name`` is the bug that silently killed every AOE and TRIGGER
    modifier in the corpus.
    """
    from kirby_combat.models import AttackInput, DiceValues

    target = session.combatants[action.target_id]
    power = action._attack_view
    if power is None:
        raise UnresolvableAction(action.kind, action.action_id)

    attack = AttackInput(
        attacker=actor, target=target, power=power,
        distance_m=None, aim=None,
        dice=DiceValues(
            to_hit=roller.roll_dice(3),
            damage=roller.roll_dice(max(1, int(power.damage_dice))),
        ),
    )
    new_session, result = resolve_attack_in_session(
        session, attack, template, action_type="attack",
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


@resolves("mental_blast")
def _resolve_mental_blast(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """A Mental Blast. 6E1 p.249: STUN only, no BODY, no Knockback."""
    target = session.combatants[action.target_id]
    power = action._attack_view
    dice = max(1, int(getattr(power, "damage_dice", 1) or 1))
    new_session, result = resolve_mental_blast_in_session(
        session, actor, target, roller.roll_dice(dice),
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


@resolves("recover")
def _resolve_recover(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Take a Recovery as this Phase's Action (6E2 p.130).

    Distinct from the free Post-Segment 12 Recovery, which the Turn wrap
    applies to everyone; this is the actor spending their Phase on it.
    ``compute_recovery``'s "phase_12" branch already bounds the gain by
    ``max_stun - current_stun`` and returns ``(0, 0)`` for a KO'd
    combatant, so no clamping is applied on top of it here.
    """
    import uuid
    from dataclasses import replace
    from datetime import datetime, timezone

    from kirby_combat.resolution.recovery import compute_recovery
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import RecoveryTaken, make_author_engine
    from kirby_combat.vitals import apply_vitals_delta

    stun_delta, end_delta = compute_recovery(actor, template, "phase_12")
    recovered = apply_vitals_delta(actor, stun=stun_delta, end=end_delta)

    # Mutate-then-log, the same two-step `_apply_post_12_recovery` uses:
    # `apply_event` records a RecoveryTaken but does not itself move anyone's
    # STUN (see `session/apply.py`).
    before = replace(
        session, combatants={**session.combatants, actor.id: recovered},
    )
    new_session = apply_event(
        before,
        session,
        RecoveryTaken(
            id=str(uuid.uuid4()),
            session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_engine(),
            combatant_id=actor.id,
            stun_recovered=stun_delta,
            end_recovered=end_delta,
        ),
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=(stun_delta, end_delta),
        events=_events_since(before, new_session),
    )


def resolve_chosen(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Execute one chosen action, returning the new session and its events.

    Raises ``UnresolvableAction`` for a kind the engine cannot yet perform.
    """
    resolver = _RESOLVERS.get(action.kind)
    if resolver is None:
        raise UnresolvableAction(action.kind, action.action_id)
    return resolver(session, actor, action, template=template, roller=roller)
