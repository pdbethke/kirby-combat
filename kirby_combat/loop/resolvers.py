"""The resolvers — one per action kind the engine can execute.

``registry.py`` holds the mechanism (the decorator, the dispatch, the
raise); this file holds the work, and is the one that grows as the driver
carve-out proceeds. Splitting them keeps the dispatch readable while the
resolver list heads toward the 52 kinds enumeration can offer.

Every resolver here has the same shape::

    @resolves("<kind>")
    def _(session, actor, action, *, template, roller) -> ResolvedAction

and the same discipline: call the engine's existing rule, never re-derive
one. Where a resolver must decide something the books do not govern --- the
placement of an Image decoy, say --- that is labelled a JUDGEMENT at the
point of decision rather than smuggled in as though it were RAW.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kirby_combat.actions.recording import (
    resolve_attack_in_session, resolve_mental_blast_in_session,
)
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import (
    ResolvedAction, UnresolvableAction, _events_since, resolves,
)
from kirby_combat.mental.recording import (
    resolve_mental_illusion_in_session, resolve_mind_control_in_session,
    resolve_telepathy_in_session,
)

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate


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


def _record_outcome(session, actor, action: LegalAction, payload: dict):
    """Emit a declaration + resolution pair carrying ``payload``.

    For resolvers whose engine rule is a PURE calculator with no session of
    its own --- Presence Attacks, the mental powers --- the outcome still
    has to reach the log, because the log is what a consumer extrudes.
    Mirrors `actions/recording.py`'s pairing exactly.
    """
    import uuid
    from datetime import datetime, timezone

    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import (
        ActionDeclared, ActionResolved, make_author_combatant,
    )

    now = datetime.now(timezone.utc)
    declared = ActionDeclared(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=now,
        author=make_author_combatant(actor.id), combatant_id=actor.id,
        action_type=action.kind,
        targets=[action.target_id] if action.target_id else [],
        parameters={},
    )
    s = apply_event(session, declared)
    resolved = ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id,
        sequence=len(s.event_log) + 1, timestamp=now,
        author=make_author_combatant(actor.id),
        declaration_event_id=declared.id, result_payload=payload,
    )
    return apply_event(s, resolved)


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


# ---------------------------------------------------------------------------
# Declarations — actions whose whole effect is that they were declared.
#
# Dodge, Set and Haymaker resolve to nothing this Phase: each records an
# intent the engine reads LATER, from the log, when something needs it.
# Dodge's +3 DCV is answered by `Dodge.dcv_bonus`, Set's +1 OCV by the Set
# action's own reader, Haymaker's +4 DC by the attack that follows. So these
# resolvers emit the declaration and stop -- there is deliberately no
# outcome to record, and inventing one would put the same rule in two places.
# ---------------------------------------------------------------------------


@resolves("dodge")
def _resolve_dodge(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Dodge (6E2 p.55): abort to a Dodge, +3 DCV against all attacks.

    ``Dodge.declare`` marks the combatant as aborting, which is what makes
    the bonus true --- ``Dodge.dcv_bonus`` reads that mark back off the log.
    """
    from kirby_combat.actions.reactive.dodge import Dodge

    new_session, _event = Dodge.declare(session, actor.id)
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=None, events=_events_since(session, new_session),
    )


@resolves("set")
def _resolve_set(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Set (6E2 p.72): spend the Phase aiming, for +1 OCV next Phase."""
    from kirby_combat.actions.set_action import Set

    new_session, _event = Set.declare(
        session, actor.id, target_id=action.target_id,
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=None, events=_events_since(session, new_session),
    )


@resolves("haymaker")
def _resolve_haymaker(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Haymaker (6E2 p.61): declare a heavier blow that lands later.

    The declaration is the whole of this Phase. The +4 DC belongs to the
    attack it modifies, which is why nothing is rolled here.
    """
    from kirby_combat.actions.haymaker import Haymaker

    new_session, _event = Haymaker.declare(session, actor.id)
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=None, events=_events_since(session, new_session),
    )


@resolves("presence_attack")
def _resolve_presence_attack(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """A Presence Attack (6E2 p.129) — PRE dice against the target's PRE.

    The outcome is an EFFECT on the target's willingness to act, not
    damage: the pure resolver classifies the roll and names the effect, and
    ``can_act_after`` says whether the target may still do anything. No
    STUN or BODY moves, so none is applied.
    """
    from kirby_combat.pre_attacks.presence import (
        base_pre_dice, resolve_presence_attack,
    )

    target = session.combatants[action.target_id]
    dice = max(1, base_pre_dice(actor))
    result = resolve_presence_attack(actor, target, roller.roll_dice(dice))

    new_session = _record_outcome(
        session, actor, action, {
            "kind": action.kind,
            "target_id": target.id,
            "effect": result.effect,
            "total": getattr(result, "total", None),
        },
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


# ---------------------------------------------------------------------------
# Powers with an engine resolver that the loop simply never reached.
#
# Flash, Entangle, Grab and Block each already had a session-aware entry
# point in `actions/`. Nothing in the engine called any of them: the parked
# driver wrote its own, so these sat behind green suites exactly as the
# mental resolvers and Images did.
#
# Each takes its numbers off `LegalAction._attack_view` -- the power object
# enumeration attached when it built the offer -- rather than re-looking-up
# by xmlid or name. An xmlid is a TYPE, not an identity: a character can
# hold two Blasts, and matching on xmlid+name is the bug that silently
# killed every AOE and TRIGGER modifier in the corpus.
# ---------------------------------------------------------------------------


def _levels(action: LegalAction, default: int = 1) -> int:
    """A power's ``levels`` --- the dice count enumeration used to write the
    offer's own summary, so menu and resolution agree by construction."""
    return max(default, int(getattr(action._attack_view, "levels", 0) or 0))


@resolves("flash")
def _resolve_flash(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Flash (6E1 p.245): blind a Sense Group for BODY − Flash Defense Segments.

    The Sense Group comes off the power via ``flash_groups``, the same
    reader Darkness and Images use. ``Flash.apply`` owns the rest ---
    including the absolute-remaining ``FlashRecovered`` bookkeeping that the
    durations pattern requires.
    """
    from kirby_combat.actions.flash import Flash
    from kirby_combat.perception import flash_groups

    power = action._attack_view
    if power is None:
        raise UnresolvableAction(action.kind, action.action_id)

    target = session.combatants[action.target_id]
    groups = sorted(flash_groups(power)) or ["sight"]
    body = sum(roller.roll_dice(_levels(action)))

    new_session, result = Flash.apply(
        session,
        attacker_id=actor.id, target_id=target.id,
        sense_group=groups[0], body_dealt=body,
        flash_defense=int(target.combat_stats().flash_defense or 0),
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


@resolves("entangle")
def _resolve_entangle(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Entangle (6E1 p.216): trap the target in something with its own BODY.

    ``Entangle.apply`` owns the escape ladder and the victim's DCV. The
    entangle's PD/ED come off the power where present; both default to the
    BODY rolled, which is the shape a plain Entangle takes.
    """
    from kirby_combat.actions.entangle import Entangle

    power = action._attack_view
    if power is None:
        raise UnresolvableAction(action.kind, action.action_id)

    body = sum(roller.roll_dice(_levels(action)))
    new_session, result = Entangle.apply(
        session,
        attacker_id=actor.id, target_id=action.target_id,
        entangle_body=body,
        entangle_pd=int(getattr(power, "entangle_pd", 0) or body),
        entangle_ed=int(getattr(power, "entangle_ed", 0) or body),
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


@resolves("grab")
def _resolve_grab(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Grab (6E2 p.67): an Attack Roll at −1 OCV to take hold.

    The −1 OCV and the grabber's −2 DCV are applied INSIDE
    ``declare_and_resolve``; the unmodified CVs are passed in, as that
    function's own docstring requires. Passing pre-penalised values would
    apply the maneuver twice.
    """
    from kirby_combat.actions.grab import Grab

    target = session.combatants[action.target_id]
    actor_stats, target_stats = actor.combat_stats(), target.combat_stats()

    new_session, result = Grab.declare_and_resolve(
        session,
        attacker_id=actor.id, target_id=target.id,
        attacker_str=int(actor_stats.str_), target_str=int(target_stats.str_),
        attacker_ocv=int(actor_stats.ocv), target_dcv=int(target_stats.dcv),
        attack_roll=sum(roller.roll_dice(3)),
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


@resolves("block")
def _resolve_block(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Block (6E2 p.51): abort to intercept an incoming attack.

    ``resolve_block_in_session`` already existed in `actions/recording.py`
    and was one of the six session-aware entry points the engine had --- and
    nothing called it either.
    """
    from kirby_combat.actions.recording import resolve_block_in_session

    target = session.combatants[action.target_id]
    new_session, result, _ids = resolve_block_in_session(
        session,
        blocker_id=actor.id, attacker_id=target.id,
        blocker_ocv=int(actor.combat_stats().ocv),
        blocker_dice=roller.roll_dice(3),
        attacker_ocv=int(target.combat_stats().ocv),
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )
