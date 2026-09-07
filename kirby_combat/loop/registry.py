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
from kirby_combat.mental.recording import (
    resolve_mental_illusion_in_session, resolve_mind_control_in_session,
    resolve_telepathy_in_session,
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


def _effect_dice(action: LegalAction, roller) -> list[int]:
    """Roll a mental power's effect dice.

    The dice count is the power's ``levels`` --- which is how enumeration
    built the offer's own summary, so the menu and the resolution agree by
    construction rather than by two readings of the same power.
    """
    power = action._attack_view
    levels = int(getattr(power, "levels", 0) or 0)
    return roller.roll_dice(max(1, levels))


@resolves("mind_control")
def _resolve_mind_control(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Mind Control. The outcome is a DEGREE against the target's EGO ---
    ego_push / simple / contrary / violent --- not damage.

    Reconnects ``kirby_combat.mental.mind_control``, which held a correct,
    tested resolver that nothing in production ever called: the parked
    driver wrote its own copy inside a 1,070-line dispatcher.
    """
    target = session.combatants[action.target_id]
    new_session, result = resolve_mind_control_in_session(
        session, actor, target, _effect_dice(action, roller),
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


@resolves("mental_illusion")
def _resolve_mental_illusion(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """A Mental Illusion, classified against EGO on the same degree ladder."""
    target = session.combatants[action.target_id]
    new_session, result = resolve_mental_illusion_in_session(
        session, actor, target, _effect_dice(action, roller),
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


@resolves("telepathy")
def _resolve_telepathy(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Telepathy --- read the target's mind, and possibly be noticed doing it."""
    target = session.combatants[action.target_id]
    new_session, result = resolve_telepathy_in_session(
        session, actor, target, _effect_dice(action, roller),
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


#: How far from the enemy a conjured decoy stands, in metres. A JUDGEMENT,
#: not RAW: 6E1 p.238 governs whether an Image is CREATED (an Attack Roll
#: against DCV 3) and whether it is BELIEVED (a PER Roll to disbelieve), and
#: says nothing about where a caster chooses to put one. Somewhere the target
#: can plainly see, close enough to be mistaken for a real combatant, is the
#: reading that makes the offer's own promise true.
DECOY_STANDOFF_M = 2.0


def _decoy_position(session: "CombatSession", actor) -> tuple[float, float, float] | None:
    """Where to conjure a decoy: between the actor and the nearest enemy.

    Enumeration's offer already committed to the policy --- its summary reads
    "Conjure an Image decoy near the nearest enemy" --- so the resolver
    honours that rather than inventing a second one. The point sits
    ``DECOY_STANDOFF_M`` short of that enemy, on the line back toward the
    caster: in the target's view, and not standing inside them.

    Returns ``None`` when the scene cannot answer --- no map, or either
    party absent from it --- and the caller refuses rather than guessing a
    coordinate.
    """
    from kirby_combat.roster import Roster
    from kirby_combat.scene.geometry import distance_3d

    scene = session.scene
    positions = getattr(scene, "combatant_positions", None) or {}
    here = positions.get(actor.id)
    if here is None:
        return None

    reachable = [
        (distance_3d(here, positions[e.id]), e.id)
        for e in Roster(session).enemies_of(actor)
        if e.id in positions
    ]
    if not reachable:
        return None

    _, nearest_id = min(reachable, key=lambda pair: (pair[0], pair[1]))
    there = positions[nearest_id]
    gap = distance_3d(here, there)
    if gap <= DECOY_STANDOFF_M:
        # Already nose to nose: put the decoy on the enemy's spot rather
        # than behind the caster, which is what a negative step would do.
        return (there.x, there.y, there.z)

    t = (gap - DECOY_STANDOFF_M) / gap
    return (
        here.x + (there.x - here.x) * t,
        here.y + (there.y - here.y) * t,
        here.z + (there.z - here.z) * t,
    )


@resolves("image_decoy")
def _resolve_image_decoy(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Conjure an Image decoy near the nearest enemy.

    Reconnects ``kirby_combat.actions.images`` --- 480 lines whose only
    importer, until now, was its own test file. The parked kirby-api driver
    re-derived the placement itself in ``_resolve_create_image_decoy``,
    which is why the engine's version sat unreachable behind a green suite.

    ``Images.place`` owns everything the books govern: the Attack Roll
    against the Image's DCV, the events, and the projected Image itself.
    This function contributes only the two things that resolver takes as
    given --- WHERE (see ``_decoy_position``, a judgement) and WHICH SENSE
    GROUPS (``images_groups``, read off the power exactly as Flash and
    Darkness read theirs).
    """
    from kirby_combat.actions.images import Images
    from kirby_combat.enumeration import images_power
    from kirby_combat.perception import images_groups

    power = images_power(actor.hero)
    if power is None:
        raise UnresolvableAction(action.kind, action.action_id)

    position = _decoy_position(session, actor)
    if position is None:
        raise UnresolvableAction(action.kind, action.action_id)

    new_session, placement = Images.place(
        session, caster_id=actor.id, position=position,
        sense_groups=sorted(images_groups(power)), roller=roller,
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=placement, events=_events_since(session, new_session),
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
