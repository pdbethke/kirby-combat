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


def _recorded(session, actor, action: LegalAction, result, payload: dict) -> "ResolvedAction":
    """Record a pure computer's outcome and wrap it as a ResolvedAction.

    The shape most of these resolvers share: the engine function returns an
    outcome and holds no session, so the outcome still has to reach the log
    for a consumer to extrude.
    """
    new_session = _record_outcome(session, actor, action, payload)
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


#: Barrier geometry. JUDGEMENTS: 6E1 p.167 sizes a Barrier from the power's
#: Area Of Effect, which a synthetic offer does not carry. These are the
#: smallest dimensions that actually block a line between two combatants.
FORCE_WALL_STANDOFF_M = 2.0
FORCE_WALL_HALF_WIDTH_M = 3.0
FORCE_WALL_HEIGHT_M = 3.0


#: How far from the enemy a conjured decoy stands, in metres. A JUDGEMENT,
#: not RAW: 6E1 p.238 governs whether an Image is CREATED (an Attack Roll
#: against DCV 3) and whether it is BELIEVED (a PER Roll to disbelieve), and
#: says nothing about where a caster chooses to put one. Somewhere the target
#: can plainly see, close enough to be mistaken for a real combatant, is the
#: reading that makes the offer's own promise true.
DECOY_STANDOFF_M = 2.0


def _point_near_nearest_enemy(
    session: "CombatSession", actor, standoff_m: float = 2.0,
) -> tuple[float, float, float] | None:
    """A point ``standoff_m`` short of the nearest enemy, toward the caster.

    Enumeration's offer already committed to the policy --- its summary reads
    "Conjure an Image decoy near the nearest enemy" --- so the resolver
    honours that rather than inventing a second one. The point sits
    ``standoff_m`` short of that enemy, on the line back toward the caster:
    in the target's view, and not standing inside them. Shared by everything
    a caster aims at a place rather than a combatant --- a decoy, a Darkness
    field --- so the two cannot drift apart.

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
    if gap <= standoff_m:
        # Already nose to nose: put the decoy on the enemy's spot rather
        # than behind the caster, which is what a negative step would do.
        return (there.x, there.y, there.z)

    t = (gap - standoff_m) / gap
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

    position = _point_near_nearest_enemy(session, actor, DECOY_STANDOFF_M)
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


@resolves("mental_entangle")
def _resolve_mental_entangle(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Mental Entangle — an ENTANGLE with Works Against EGO.

    Its BODY is reduced by the target's Mental Defense rather than PD, and
    escape is a 3d6 EGO Roll rather than a STR contest. Both live in
    `mental/mental_entangle.py`; this only rolls the dice and records.
    """
    from kirby_combat.mental.mental_entangle import apply_mental_entangle

    target = session.combatants[action.target_id]
    result = apply_mental_entangle(actor, target, roller.roll_dice(_levels(action)))
    new_session = _record_outcome(session, actor, action, {
        "kind": action.kind,
        "target_id": target.id,
        "entangle_body": result.state.entangle_body,
    })
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


# ---------------------------------------------------------------------------
# Adjustment powers.
#
# THESE NOW FADE (2026-09-07). When this was written, `AdjustmentFaded` had
# no emitter anywhere in the engine -- the class existed, `apply_event`
# passed it through, `session/effects.py` folded it, and nothing ever
# constructed one, so an Aid or Drain lasted forever. `encounter.py`'s
# `_apply_adjustment_fade` is that emitter, firing on the Turn wrap beside
# the Post-Segment 12 Recovery.
#
# The fade rate is carried on the event, which is why a power with a
# bought-up rate keeps its own rather than being fixed at 5.
#
# AND THEY NOW APPLY (2026-09-07). `kirby_combat/adjustments.py` is the
# read surface, following the seam `cv_modifiers.py` established for
# Stunned: the base comes from the build, the session supplies the
# modifier, and the two compose at the point of use. Wired into the CV path
# and the Stunning check -- an Aided OCV hits more often, a Drained CON
# Stuns to blows that would otherwise fall short. A caller reading
# `combat_stats()` directly still gets the unadjusted value; see that
# module for what the seam does and does not reach.
# ---------------------------------------------------------------------------


def _adjustment(
    session: "CombatSession", actor, action: LegalAction, *, roller, sign: str,
) -> ResolvedAction:
    """Shared body for Aid and Drain: roll, compute, record, apply."""
    import uuid
    from datetime import datetime, timezone

    from kirby_combat.resolution.adjustments import compute_aid, compute_drain
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import AdjustmentApplied, make_author_combatant

    #: 6E: an Adjustment power's dice are its levels; 5 Active Points buys
    #: one point of effect, which is the engine's `points_per_level`.
    rolled = sum(roller.roll_dice(_levels(action)))
    target_id = action.target_id or actor.id
    target = session.combatants[target_id]

    if sign == "aid":
        outcome = compute_aid(rolled, 5, target_max_boost_cp=rolled)
    else:
        outcome = compute_drain(
            rolled, 5, target_current_value=int(target.state.current_stun),
        )

    new_session = _record_outcome(session, actor, action, {
        "kind": action.kind,
        "target_id": target_id,
        "delta": outcome.delta,
        "fade_rate_per_turn": outcome.fade_rate_per_turn,
    })
    new_session = apply_event(new_session, AdjustmentApplied(
        id=str(uuid.uuid4()), session_id=new_session.id,
        sequence=len(new_session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(actor.id),
        target_id=target_id, stat="STUN",
        delta=outcome.delta, fade_rate_per_turn=outcome.fade_rate_per_turn,
    ))
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=outcome, events=_events_since(session, new_session),
    )


@resolves("aid")
def _resolve_aid(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Aid (6E1 p.133): a positive, fading boost. Targets an ally, or the
    actor when the offer names no one."""
    return _adjustment(session, actor, action, roller=roller, sign="aid")


@resolves("drain")
def _resolve_drain(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Drain (6E1 p.139): a negative, fading reduction, capped so it cannot
    take the target below zero."""
    return _adjustment(session, actor, action, roller=roller, sign="drain")


def _decoy_position(session: "CombatSession", actor):
    """Backwards-compatible alias used by the Images tests."""
    return _point_near_nearest_enemy(session, actor, DECOY_STANDOFF_M)


# ---------------------------------------------------------------------------
# Maneuvers and multi-shot attacks.
#
# These engine functions are PURE COMPUTERS -- they return an outcome and
# hold no session -- so each wrapper rolls what the rule needs, calls it
# unchanged, and records the result. None re-derives a number the engine
# already knows how to produce.
# ---------------------------------------------------------------------------


def _velocity_mps(actor) -> float:
    """The actor's velocity at impact: a full Move, in metres per Phase.

    6E2 p.18 makes a Segment one second, and a full Move covers the
    character's full RUNNING in a Phase, so metres-per-Phase is the figure a
    Move-By or Move-Through wants. Read from the build rather than assumed.
    """
    return float(actor.hero.characteristic_value("RUNNING") or 0)


@resolves("move_by")
def _resolve_move_by(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Move-By (6E2 p.64): strike in passing, taking a third of the damage back."""
    from kirby_combat.actions.move_by import MoveBy

    stats = actor.combat_stats()
    outcome = MoveBy.compute(
        attacker_str=int(stats.str_), velocity_mps=_velocity_mps(actor),
    )
    return _recorded(session, actor, action, outcome, {
        "kind": action.kind, "target_id": action.target_id,
        "damage_dc": getattr(outcome, "damage_dc", None),
    })


@resolves("move_through")
def _resolve_move_through(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Move-Through (6E2 p.65): commit to the charge, and take more back."""
    from kirby_combat.actions.move_through import MoveThrough

    stats = actor.combat_stats()
    outcome = MoveThrough.compute(
        attacker_str=int(stats.str_), velocity_mps=_velocity_mps(actor),
    )
    return _recorded(session, actor, action, outcome, {
        "kind": action.kind, "target_id": action.target_id,
        "damage_dc": getattr(outcome, "damage_dc", None),
    })


@resolves("rapid_fire")
def _resolve_rapid_fire(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Rapid Fire (6E2 p.73): several shots this Phase at a widening penalty.

    ``num_shots`` is 2 --- the fewest that make it Rapid Fire, and the
    cheapest in OCV. Choosing MORE is a tactical decision the offer does not
    carry, so taking the minimum is the reading that cannot overreach on the
    chooser's behalf.
    """
    from kirby_combat.actions.rapid_fire import RapidFire

    outcome = RapidFire.compute(
        base_ocv=int(actor.combat_stats().ocv), num_shots=2,
    )
    return _recorded(session, actor, action, outcome, {
        "kind": action.kind, "target_id": action.target_id,
        "shot_ocvs": list(outcome.per_shot_ocv),
    })


@resolves("throw", "throw_object")
def _resolve_throw(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Throw (6E2 p.75): hurl a held combatant or object.

    ``Throw.compute`` derives both distance and damage from STR; at maximum
    range when no distance is asked for, which is what an offer with no
    distance on it means.
    """
    from kirby_combat.actions.throw import Throw

    outcome = Throw.compute(attacker_str=int(actor.combat_stats().str_))
    return _recorded(session, actor, action, outcome, {
        "kind": action.kind, "target_id": action.target_id,
        "distance_m": getattr(outcome, "distance_m", None),
    })


@resolves("maneuver")
def _resolve_maneuver(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """A martial maneuver (6E2 p.78): declare it, and the attack reads it.

    Like Set and Haymaker, the declaration IS this Phase. ``MartialArts``
    computes the maneuver's CV and DC modifiers, and the attack that follows
    reads them via ``modifiers_for_pending_attack``.
    """
    from kirby_combat.actions.martial_arts import MARTIAL_MANEUVERS, MartialArts

    # The offer names the maneuver in `power_xmlid`. `MartialArts.declare`
    # raises on an id it does not know, which is the right behaviour -- a
    # maneuver the engine cannot model must not resolve as though it did --
    # so an unknown one is reported as unresolvable rather than swallowed.
    maneuver_id = action.power_xmlid
    if maneuver_id not in MARTIAL_MANEUVERS:
        raise UnresolvableAction(action.kind, action.action_id)

    new_session, _event = MartialArts.declare(
        session, actor.id, maneuver_id=maneuver_id,
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=None, events=_events_since(session, new_session),
    )


# ---------------------------------------------------------------------------
# Held actions and placed fields.
# ---------------------------------------------------------------------------


@resolves("hold")
def _resolve_hold(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Hold an Action (6E2 p.20): spend the Phase waiting for a trigger."""
    from kirby_combat.actions.held_action import HeldAction

    new_session, _event = HeldAction.declare(
        session, actor.id,
        trigger_condition=action.summary or "a trigger of the actor's choosing",
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=None, events=_events_since(session, new_session),
    )


@resolves("release_held")
def _resolve_release_held(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Release a held Action --- its trigger has fired.

    The offer's ``action_id`` carries the held event's id, since a combatant
    may be holding more than one and the engine must release the one the
    chooser picked rather than whichever comes first.
    """
    from kirby_combat.actions.held_action import HeldAction

    held_id = action.action_id.split(":", 1)[-1]
    pending = {e.id for e in HeldAction.get_pending(session, actor.id)}
    if held_id not in pending:
        raise UnresolvableAction(action.kind, action.action_id)

    new_session, _event = HeldAction.release(
        session, held_id, trigger_observed="the actor judged the moment right",
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=None, events=_events_since(session, new_session),
    )


#: Half-width of a placed Darkness field, in metres. A JUDGEMENT: 6E1 p.140
#: sizes the field from the power's Area Of Effect, which a synthetic offer
#: does not carry, and this is the smallest square that meaningfully occludes.
DARKNESS_HALF_WIDTH_M = 2.0


@resolves("darkness_zone")
def _resolve_darkness_zone(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Darkness (6E1 p.140): put a field on the scene that blocks a Sense Group.

    ``Darkness.place`` owns the Attack Roll and the construct, including the
    one-zone-per-Sense-Group rule its docstring insists on. This contributes
    only WHERE (the shared placement helper, a judgement) and the groups,
    read off the power by ``darkness_groups`` --- the same reader Flash and
    Images use.
    """
    from kirby_combat.actions.darkness import Darkness
    from kirby_combat.enumeration import darkness_power
    from kirby_combat.perception import darkness_groups, darkness_personal_immunity

    power = action._attack_view or darkness_power(actor.hero)
    if power is None:
        raise UnresolvableAction(action.kind, action.action_id)

    centre = _point_near_nearest_enemy(session, actor, DARKNESS_HALF_WIDTH_M)
    if centre is None:
        raise UnresolvableAction(action.kind, action.action_id)

    x, y, z = centre
    h = DARKNESS_HALF_WIDTH_M
    new_session, result = Darkness.place(
        session,
        attacker_id=actor.id,
        polygon_xy=[(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)],
        elevation_range_m=(z, z + 2 * h),
        sense_groups=sorted(darkness_groups(power)) or ["sight"],
        personal_immunity=darkness_personal_immunity(power),
        roller=roller,
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


# ---------------------------------------------------------------------------
# Escaping an Entangle.
#
# 6E1 p.218 lists the routes out, and the engine already implements all of
# them. The BODY an escape attempt does soaks against the ENTANGLE's PD/ED,
# never the victim's -- `escape_attempt` takes that already applied, which
# is why the roll happens here and the rule does not.
# ---------------------------------------------------------------------------


@resolves("escape_str")
def _resolve_escape_str(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Escape by main force: a STR attempt against the Entangle's BODY."""
    from kirby_combat.actions.entangle import Entangle, str_escape_dice

    dice = max(1, str_escape_dice(int(actor.combat_stats().str_)))
    new_session, result = Entangle.escape_attempt(
        session, target_id=actor.id,
        damage_body=sum(roller.roll_dice(dice)), escape_type="full",
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


@resolves("escape_attack")
def _resolve_escape_attack(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Escape by attacking the Entangle with a power rather than with STR."""
    from kirby_combat.actions.entangle import Entangle

    power = action._attack_view
    dice = max(1, int(getattr(power, "damage_dice", 0) or 0)) if power else 1
    new_session, result = Entangle.escape_attempt(
        session, target_id=actor.id,
        damage_body=sum(roller.roll_dice(dice)), escape_type="full",
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


@resolves("escape_teleport")
def _resolve_escape_teleport(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Teleport out (6E1 p.218): no Attack Roll, no BODY --- simply elsewhere.

    An Entangle bought Cannot Be Escaped With Teleportation refuses it
    unless the Teleportation carries at least as many levels of Armor
    Piercing. `teleport_escape` owns that comparison; the AP levels are read
    off the escaper's own power.
    """
    from kirby_combat.actions.entangle import Entangle

    power = action._attack_view
    new_session, result = Entangle.teleport_escape(
        session, target_id=actor.id,
        teleport_ap_levels=int(getattr(power, "armor_piercing_levels", 0) or 0),
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


# ---------------------------------------------------------------------------
# Constructs, fields and the remaining adjustments.
# ---------------------------------------------------------------------------


@resolves("attack_construct")
def _resolve_attack_construct(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Attack a thing rather than a person --- a wall, a door, a debris pile.

    6E2 p.172: objects take BODY and break; they have no STUN behaviour at
    all. `apply_attack_to_construct` owns that, including the DEF an attack
    must beat.
    """
    from kirby_combat.resolution.object_damage import apply_attack_to_construct

    scene = session.scene
    target_id = action.target_id
    construct = next(
        (c for c in (getattr(scene, "constructs", None) or [])
         if getattr(c, "id", None) == target_id),
        None,
    )
    if construct is None:
        raise UnresolvableAction(action.kind, action.action_id)

    power = action._attack_view
    dice = max(1, int(getattr(power, "damage_dice", 0) or 0)) if power else 1
    outcome = apply_attack_to_construct(
        construct, body_dealt=sum(roller.roll_dice(dice)),
    )
    return _recorded(session, actor, action, outcome, {
        "kind": action.kind, "target_id": target_id,
    })


@resolves("heal")
def _resolve_heal(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Healing (6E1 p.150): restore a stat, and unlike Aid it does not fade.

    Shares Aid's arithmetic --- both add points at 1 per 5 Active Points ---
    which is why `compute_aid` is the right calculator. What differs is the
    FADE, and Healing has none, so no AdjustmentApplied is emitted: an event
    carrying `fade_rate_per_turn=5` would say the opposite of the rule.
    """
    from kirby_combat.resolution.adjustments import compute_aid

    rolled = sum(roller.roll_dice(_levels(action)))
    target_id = action.target_id or actor.id
    outcome = compute_aid(rolled, 5, target_max_boost_cp=rolled)
    return _recorded(session, actor, action, outcome, {
        "kind": action.kind, "target_id": target_id, "delta": outcome.delta,
    })


@resolves("dispel")
def _resolve_dispel(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Dispel (6E1 p.143): shut a power off outright rather than weaken it.

    All-or-nothing against the target power's Active Points, which is why
    the payload records the roll rather than a delta --- there is no partial
    Dispel to apply.
    """
    rolled = sum(roller.roll_dice(_levels(action)))
    return _recorded(session, actor, action, rolled, {
        "kind": action.kind,
        "target_id": action.target_id,
        "active_points_rolled": rolled,
    })


@resolves("presence_attack_group")
def _resolve_presence_attack_group(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """A Presence Attack on everyone who can perceive it.

    6E2 p.129 makes a Presence Attack an effect on those who witness it, so
    a group attack is the SAME roll judged against each target's PRE --- not
    a fresh roll per victim. Rolling once and reusing the total is what
    makes the "one terrifying moment" a single event rather than several.
    """
    from kirby_combat.pre_attacks.presence import base_pre_dice, resolve_presence_attack
    from kirby_combat.roster import Roster

    dice_values = roller.roll_dice(max(1, base_pre_dice(actor)))
    results = {
        enemy.id: resolve_presence_attack(actor, enemy, dice_values)
        for enemy in Roster(session).enemies_of(actor)
    }
    if not results:
        raise UnresolvableAction(action.kind, action.action_id)

    return _recorded(session, actor, action, results, {
        "kind": action.kind,
        "effects": {tid: r.effect for tid, r in results.items()},
    })


@resolves("push")
def _resolve_push(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Push a power (6E2 p.133): +1 DC for +5 END.

    The offer promises exactly one DC for exactly five END, so this resolves
    the attack it names with one extra Damage Class and spends the END. It
    does NOT re-derive the exchange rate --- that is the offer's summary and
    the book's, not a number invented here.
    """
    from kirby_combat.models import AttackInput, DiceValues
    from kirby_combat.vitals import apply_vitals_delta

    power = action._attack_view
    if power is None:
        raise UnresolvableAction(action.kind, action.action_id)

    target = session.combatants[action.target_id]
    dice = max(1, int(power.damage_dice or 0)) + 1      # the pushed Damage Class
    attack = AttackInput(
        attacker=actor, target=target, power=power,
        distance_m=None, aim=None,
        dice=DiceValues(to_hit=roller.roll_dice(3), damage=roller.roll_dice(dice)),
    )
    new_session, result = resolve_attack_in_session(
        session, attack, template, action_type="attack",
    )
    # 6E2 p.133's price. The engine applies no END for a Push anywhere else,
    # so it is spent here rather than left owed.
    pushed = apply_vitals_delta(new_session.combatants[actor.id], end=-5)
    from dataclasses import replace as _replace

    new_session = _replace(
        new_session, combatants={**new_session.combatants, actor.id: pushed},
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


@resolves("hide")
def _resolve_hide(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Hide --- a Stealth attempt against every watcher's PER.

    Contested per observer, because being unseen is not a property of the
    hider: one enemy may lose you while another keeps you in view. The
    engine's `_opposed_perceives` is the contest; this only supplies the two
    target numbers and records who lost track of whom.
    """
    from kirby_combat.perception import _opposed_perceives
    from kirby_combat.roster import Roster

    stats = actor.combat_stats()
    #: 6E1 p.60: a Characteristic Roll is 9 + CHAR/5.
    stealth_target = 9 + int(stats.dex) // 5

    unseen_by: list[str] = []
    for enemy in Roster(session).enemies_of(actor):
        per_target = 9 + int(enemy.combat_stats().int_) // 5
        perceives, _p, _s = _opposed_perceives(per_target, stealth_target, roller)
        if not perceives:
            unseen_by.append(enemy.id)

    return _recorded(session, actor, action, tuple(unseen_by), {
        "kind": action.kind, "unseen_by": unseen_by,
    })


@resolves("force_wall")
def _resolve_force_wall(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Raise a Barrier (6E1 p.167) between the actor and the nearest enemy.

    The wall's BODY and DEF come from the power's levels. WHERE it goes is a
    judgement, and the same one a decoy and a Darkness field make --- the
    shared placement helper --- because a barrier that is not between you
    and the threat is not a barrier.
    """
    from kirby_combat.scene.scene import Position, Wall

    power = action._attack_view
    if power is None:
        raise UnresolvableAction(action.kind, action.action_id)

    scene = session.scene
    centre = _point_near_nearest_enemy(session, actor, FORCE_WALL_STANDOFF_M)
    if scene is None or centre is None:
        raise UnresolvableAction(action.kind, action.action_id)

    x, y, z = centre
    levels = _levels(action)
    half = FORCE_WALL_HALF_WIDTH_M
    wall = Wall(
        id=f"force-wall-{actor.id}-{len(getattr(scene, 'walls', []) or [])}",
        name="Force Wall",
        segment=(Position(x - half, y, z), Position(x + half, y, z)),
        height_m=FORCE_WALL_HEIGHT_M,
        body=levels, def_value=levels, ed_value=levels,
    )
    scene.walls.append(wall)
    return _recorded(session, actor, action, wall, {
        "kind": action.kind, "wall_id": wall.id, "body": levels,
    })


# ---------------------------------------------------------------------------
# Movement — the kinds that were blocked on nobody writing a position down.
#
# `scene/movement_legality.movement_reach` has always decided where a mover
# ends up, clamped by walls, surfaces and capacity. `scene/placement.py` is
# the step that records it. Neither judges the other's business: the first
# never moves anybody, the second never decides legality.
# ---------------------------------------------------------------------------


def _move_capacity(actor, mode: str) -> float:
    """How far this mover can go in a Phase, by mode.

    RUNNING is the characteristic every character has; other modes are
    powers, read off the build by the same name. A mode the build cannot do
    has no capacity, which `movement_reach` then treats as "cannot get
    there" rather than as an error.
    """
    return float(actor.hero.characteristic_value(mode.upper()) or 0)


def _half_move(actor, mode: str = "running") -> float:
    """A Half Move --- what a combatant covers while still attacking (6E2 p.42)."""
    return _move_capacity(actor, mode) / 2.0


@resolves("move")
def _resolve_move(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Close on the named enemy.

    A full Move, since this offer carries no attack --- the actor is
    spending the whole Phase getting there. Where they actually end up is
    `movement_reach`'s call, not this function's: a wall, a missing
    supporting surface or plain distance may leave them short, and a partial
    move is a real move.
    """
    from kirby_combat.scene.placement import move_toward, position_of

    mode = action.mode or "running"
    destination = position_of(session.scene, action.target_id)
    if destination is None:
        raise UnresolvableAction(action.kind, action.action_id)

    new_session, outcome = move_toward(
        session, actor.id, destination,
        mode=mode, distance_m=_move_capacity(actor, mode),
    )
    if outcome is None:
        raise UnresolvableAction(action.kind, action.action_id)

    return _recorded(new_session, actor, action, outcome, {
        "kind": action.kind, "target_id": action.target_id, "mode": mode,
        "reached": outcome.reachable,
        "landing": [outcome.landing.x, outcome.landing.y, outcome.landing.z],
    })


def _reposition(session, actor, action, *, roller, then_attack: bool):
    """Shared body for the four reposition kinds.

    Each offer already chose its destination --- enumeration put it on
    ``reposition_dest`` --- so the resolver moves there and, for the
    strike variants, resolves the attack from the new position. Re-deciding
    the destination here would mean the menu advertised one place and the
    engine went to another.
    """
    from kirby_combat.models import AttackInput, DiceValues
    from kirby_combat.scene.placement import move_toward
    from kirby_combat.scene.scene import Position

    if action.reposition_dest is None:
        raise UnresolvableAction(action.kind, action.action_id)

    mode = action.mode or "running"
    x, y, z = action.reposition_dest
    new_session, outcome = move_toward(
        session, actor.id, Position(x, y, z),
        mode=mode, distance_m=_move_capacity(actor, mode),
    )
    if outcome is None:
        raise UnresolvableAction(action.kind, action.action_id)

    payload = {
        "kind": action.kind, "target_id": action.target_id, "mode": mode,
        "reached": outcome.reachable,
        "landing": [outcome.landing.x, outcome.landing.y, outcome.landing.z],
    }

    power = action._attack_view
    if not (then_attack and power is not None and action.target_id):
        return _recorded(new_session, actor, action, outcome, payload)

    # The strike happens FROM the landing point, which is the whole reason
    # these are one action rather than two: the move buys the shot.
    target = new_session.combatants[action.target_id]
    attack = AttackInput(
        attacker=new_session.combatants[actor.id], target=target, power=power,
        distance_m=None, aim=None,
        dice=DiceValues(
            to_hit=roller.roll_dice(3),
            damage=roller.roll_dice(max(1, int(power.damage_dice or 0))),
        ),
    )
    after, result = resolve_attack_in_session(
        new_session, attack, session.template, action_type="attack",
    )
    return ResolvedAction(
        session=after, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, after),
    )


@resolves("reposition", "reposition_vantage", "reposition_push")
def _resolve_reposition(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Move to a chosen point --- for cover, for a vantage, or to shove past.

    No attack follows: the destination IS the action. `reposition_vantage`
    differs only in why enumeration picked the point (a line of sight it
    wanted), which is already baked into ``reposition_dest``.
    """
    return _reposition(session, actor, action, roller=roller, then_attack=False)


@resolves("reposition_strike", "move_strike")
def _resolve_reposition_strike(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Move, then strike from where you land.

    `move_strike` closes on the target; `reposition_strike` goes to a point
    enumeration chose. Both end in an attack resolved from the NEW position,
    which is what makes them a single action rather than two.
    """
    from kirby_combat.scene.placement import position_of

    if action.reposition_dest is None and action.target_id:
        # `move_strike` names an enemy rather than a point: close on them.
        destination = position_of(session.scene, action.target_id)
        if destination is None:
            raise UnresolvableAction(action.kind, action.action_id)
        object.__setattr__(
            action, "reposition_dest",
            (destination.x, destination.y, destination.z),
        )
    return _reposition(session, actor, action, roller=roller, then_attack=True)


@resolves("pickup")
def _resolve_pickup(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Pick up an adjacent debris chunk, to throw next Phase.

    Enumeration already applied every gate the rule has --- the chunk is
    within reach, the actor is not already holding one, STR is enough to
    lift it. What is left is recording that they now hold it, keyed by the
    construct id the offer names.
    """
    obj_id = action.action_id.split(":", 1)[-1]
    if not obj_id:
        raise UnresolvableAction(action.kind, action.action_id)
    return _recorded(session, actor, action, obj_id, {
        "kind": action.kind, "object_id": obj_id,
    })


# ---------------------------------------------------------------------------
# The three maneuvers that had NO ENGINE RULE — sub-project B.
#
# Unlike everything above, these were not unwired rules waiting for a caller.
# Nothing in the engine implemented them at all. Each is an Attack Roll at a
# CV penalty with a specific consequence, and each citation below comes from
# enumeration's own offer summary -- the menu has been promising these exact
# numbers to choosers all along, with nothing behind them.
# ---------------------------------------------------------------------------


def _maneuver_attack(
    session, actor, action: LegalAction, *, roller, ocv_modifier: int,
    damage_dice: int | None = None, action_type: str = "strike",
):
    """An Attack Roll at a maneuver's CV penalty.

    Goes through `resolve_attack_in_session` rather than rolling to-hit by
    hand, so a maneuver gets every rule a normal attack gets -- CV
    modifiers, the hit determination, damage application -- instead of a
    second, thinner copy of the resolution path.
    """
    from kirby_combat.models import AttackInput, DiceValues

    power = action._attack_view or next(iter(actor.attacks or []), None)
    if power is None:
        raise UnresolvableAction(action.kind, action.action_id)

    target = session.combatants[action.target_id]
    dice = damage_dice if damage_dice is not None else int(power.damage_dice or 0)
    attack = AttackInput(
        attacker=actor, target=target, power=power,
        distance_m=None, aim=None,
        dice=DiceValues(
            to_hit=roller.roll_dice(3),
            damage=roller.roll_dice(max(0, dice)) if dice > 0 else [],
        ),
        ocv_modifier=ocv_modifier,
    )
    return resolve_attack_in_session(session, attack, session.template,
                                     action_type=action_type)


@resolves("trip")
def _resolve_trip(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Trip (6E2 p.67): −1 OCV, no damage, and on a hit the target goes prone.

    THE CONSEQUENCE NOW HAS SOMEWHERE TO LIVE. `prone` was a documented gap
    in `statuses.py` --- its consumers existed (`scene/cover.py` takes
    `target_is_prone_or_diving`, `actions/martial_arts.py` has
    `target_falls`) and nothing could ever set it. This resolver is that
    source: the payload carries `kind="trip"` and `hit`, and
    `statuses._is_prone` folds it.

    No damage: the Attack Roll decides whether they go down, and that is
    the whole effect.
    """
    from dataclasses import replace as _replace

    new_session, result = _maneuver_attack(
        session, actor, action, roller=roller, ocv_modifier=-1, damage_dice=0,
    )
    # Re-stamp the payload so the fold can see `kind="trip"` -- the attack
    # wrapper labels it "strike", which is what it mechanically is.
    log = list(new_session.event_log)
    last = log[-1]
    log[-1] = _replace(last, result_payload={
        **last.result_payload, "kind": "trip", "target_id": action.target_id,
    })
    new_session = _replace(new_session, event_log=log)

    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


@resolves("disarm")
def _resolve_disarm(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Disarm (6E2 p.65): −2 OCV to knock a weapon out of the target's hand.

    THE ATTACK ROLL IS REAL; THE DISARMING IS NOT YET. This engine does not
    track weapons per combatant --- there is no inventory to remove one from
    --- so a successful Disarm lands in the log and takes nothing away.
    Enumeration has said so in its own comment since the offer was written
    ("v1 narrative-only ... doesn't mechanically remove a weapon"), and this
    resolver matches that rather than pretending otherwise. When weapons
    become first-class, the hit recorded here is what a consequence hangs
    off.
    """
    new_session, result = _maneuver_attack(
        session, actor, action, roller=roller, ocv_modifier=-2, damage_dice=0,
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


#: Dice traded for OCV by a Spread. The offer is built with exactly two
#: (`enumeration.py` appends `:2` to the action_id), so the resolver reads
#: it off the id rather than assuming.
SPREAD_DEFAULT_DICE = 2


@resolves("spread")
def _resolve_spread(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Spread (6E2 p.52): sacrifice damage dice, one for one, for OCV.

    The trade is symmetrical --- N fewer dice buys +N OCV --- and the count
    rides on the action_id's trailing `:N`, because that is where
    enumeration put it when it wrote the offer. Reading it back means the
    menu and the resolution cannot disagree about how many dice were sold.
    """
    power = action._attack_view
    if power is None:
        raise UnresolvableAction(action.kind, action.action_id)

    tail = action.action_id.rsplit(":", 1)[-1]
    spread = int(tail) if tail.isdigit() else SPREAD_DEFAULT_DICE
    base = int(power.damage_dice or 0)
    if spread >= base:
        # Selling every die buys OCV for an attack that cannot hurt anyone.
        raise UnresolvableAction(action.kind, action.action_id)

    new_session, result = _maneuver_attack(
        session, actor, action, roller=roller,
        ocv_modifier=+spread, damage_dice=base - spread, action_type="attack",
    )
    return ResolvedAction(
        session=new_session, kind=action.kind, action_id=action.action_id,
        result=result, events=_events_since(session, new_session),
    )


# ---------------------------------------------------------------------------
# The last three — the ones that needed machinery rather than wiring.
# ---------------------------------------------------------------------------


@resolves("coordinate")
def _resolve_coordinate(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Join a coordinated strike (6E2 p.46).

    A Teamwork roll --- or Tactics, or a flat DEX 8- for a character with
    neither --- to time this Phase's blow with an ally's. The window lives
    in the log and `coordination.window_for` folds it; nothing is held in a
    dict on the session, for the same reason `session/effects.py` gives.

    THE POOL IS APPLIED. 6E2 p.46's payoff --- participants' STUN pooled
    against the target's CON, so two blows that each fall short can
    together Stun --- happens as a DERIVATION rather than by rescheduling
    attacks to resolve simultaneously, which a one-actor-per-Phase loop
    cannot do. `statuses._is_stunned` reads the pool as a second SET source
    alongside a single attack's own `status_changes`. See
    `kirby_combat/coordination.py` for why the derivation is the honest
    mechanism and not a workaround.
    """
    from kirby_combat.coordination import CoordinationRoll, roll_profile

    skill, target_number = roll_profile(actor)
    attempt = CoordinationRoll(
        combatant_id=actor.id, target_id=action.target_id,
        skill=skill, target_number=target_number,
        roll=sum(roller.roll_dice(3)),
    )
    return _recorded(session, actor, action, attempt, {
        "kind": action.kind,
        "combatant_id": actor.id,
        "target_id": action.target_id,
        "segment": session.timeline.segment,
        "skill": skill,
        "target_number": target_number,
        "roll": attempt.roll,
        "joined": attempt.joined,
    })


@resolves("reallocate")
def _resolve_reallocate(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Change which slots of a Multipower are active.

    The offer names the framework and the slots it is offering, in its
    action_id (`reallocate_slots:<framework>:<slot,slot,...>`), so the
    resolver reads both back rather than re-deriving them --- the menu
    chose the set, and re-deciding here would change it after the fact.

    Recorded, not applied to a combatant: framework state is not a field on
    any combatant in this engine. `enumerate_actions` takes
    `slot_allocation` as a PARAMETER, so the active set has always been the
    caller's to hold; `framework.active_slots` now folds it out of the log
    so a caller can read it back instead of tracking it separately.
    """
    from kirby_combat.framework import (
        ReserveExceeded, parse_reallocation, validate_allocation,
    )

    framework_id, slot_ids = parse_reallocation(action.action_id)
    if not framework_id:
        raise UnresolvableAction(action.kind, action.action_id)

    # THE RESERVE IS ENFORCED HERE, not assumed from the menu. 6E1 p.204:
    # a Multipower's reserve is the total Active Points its slots may draw
    # AT ONCE, and that constraint is the entire reason a framework is
    # cheaper than buying the powers outright. `enumerate_actions` gates
    # which slots it OFFERS, but an offer is not a permission slip -- a
    # reallocate names its whole set in one id, so a chooser returning a
    # hand-built id would otherwise switch on a configuration the build
    # cannot pay for.
    try:
        drawn = validate_allocation(actor, framework_id, slot_ids)
    except (ReserveExceeded, KeyError) as exc:
        raise UnresolvableAction(action.kind, action.action_id) from exc

    return _recorded(session, actor, action, (framework_id, slot_ids), {
        "kind": action.kind,
        "combatant_id": actor.id,
        "framework_id": framework_id,
        "active_slot_ids": list(slot_ids),
        "active_points_drawn": drawn,
    })


@resolves("reconfigure_vpp")
def _resolve_reconfigure_vpp(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Reconfigure a Variable Power Pool --- record the intent.

    WHAT THIS DELIBERATELY DOES NOT DO: build the power. The offer says
    "build a new power from the catalog", and constructing a costed power
    is the BUILD engine's work (kirby-cost), not combat's. Combat consumes
    the build engine's shape; it does not become a second one. A consumer
    builds the power, checks it against the pool, and brings it back as a
    normal attack power.

    So this records that the pool was opened for reconfiguration, keyed by
    framework, which is the part that belongs to the fight. Doing more here
    would put cost math in the combat engine --- the exact thing the north
    star forbids.
    """
    from kirby_combat.framework import parse_reallocation

    framework_id, _slots = parse_reallocation(action.action_id)
    if not framework_id:
        raise UnresolvableAction(action.kind, action.action_id)

    return _recorded(session, actor, action, framework_id, {
        "kind": action.kind,
        "combatant_id": actor.id,
        "framework_id": framework_id,
    })


# ---------------------------------------------------------------------------
# The eight kinds a literal-only AST scan could not see.
#
# `enumerate_actions` builds three of its offers with a COMPUTED kind --
# `kind = "sweep" if is_hth else "multiple_attack"`, the interaction-skill
# loop, and the climb loop -- so a scan matching `kind="literal"` counted 51
# where the real total is 59. The "every offered kind is registered" test was
# passing against an incomplete set, which is why `ALL_ACTION_KINDS` now
# names them all in one place instead.
#
# Found by running the O.K. Corral: 27 of 31 model picks came back
# `multiple_attack` and were skipped, in a fight the count said was fully
# covered.
# ---------------------------------------------------------------------------


def _multi_attack(session, actor, action, *, roller, sweep: bool):
    """Sweep (6E2 p.56) and Multiple Attack (6E2 p.71): several targets in
    one Phase at a widening OCV penalty, and half DCV for the whole Phase.

    Identical arithmetic --- `Sweep.compute` delegates to
    `MultipleAttack.compute` --- and the engine keeps them as two names
    because the book does: a Sweep is hand-to-hand and can only reach what
    is already within Reach, which enumeration has already gated.

    TWO TARGETS, for the same reason Rapid Fire takes two shots: it is the
    fewest that make it a Multiple Attack and the cheapest in OCV. How many
    MORE to take is a tactical decision the offer does not carry.
    """
    from kirby_combat.actions.multiple_attack import MultipleAttack
    from kirby_combat.actions.sweep import Sweep

    compute = Sweep.compute if sweep else MultipleAttack.compute
    outcome = compute(base_ocv=int(actor.combat_stats().ocv), num_targets=2)
    return _recorded(session, actor, action, outcome, {
        "kind": action.kind, "target_id": action.target_id,
        "per_target_ocv": list(outcome.per_shot_ocv),
        "dcv_factor": outcome.dcv_factor,
    })


@resolves("sweep")
def _resolve_sweep(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Sweep --- a hand-to-hand Multiple Attack (6E2 p.56)."""
    return _multi_attack(session, actor, action, roller=roller, sweep=True)


@resolves("multiple_attack")
def _resolve_multiple_attack(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Multiple Attack --- the ranged form (6E2 p.71)."""
    return _multi_attack(session, actor, action, roller=roller, sweep=False)


def _climb(session, actor, action: LegalAction, *, fast: bool):
    """Climb a wall (6E1 p.70, 6E2 p.48-49).

    `climbing.py` owns the rule, including the contradiction it resolves:
    6E1 p.70 halves OCV *and* DCV, 6E2 p.48-49 halves DCV only and takes -2
    DC. The engine implements 6E2. What this adds is the wall id, read off
    the offer, and whether the climber is hurrying.
    """
    from kirby_combat.climbing import climb_modifiers, climb_status

    # `climb_wall_id` is the offer's own field; the action_id is the
    # fallback for a hand-built action. Split only when there IS a
    # separator -- `"climb".split(":", 1)[-1]` returns "climb", so an
    # unqualified id would name the KIND as the wall and climb it.
    wall_id = action.climb_wall_id
    if not wall_id and ":" in action.action_id:
        wall_id = action.action_id.split(":", 1)[1]
    if not wall_id:
        raise UnresolvableAction(action.kind, action.action_id)

    mods = climb_modifiers(0)
    return _recorded(session, actor, action, mods, {
        "kind": action.kind,
        "wall_id": wall_id,
        "status": climb_status(wall_id),
        "dcv_delta": mods.dcv_delta,
        "dcv_multiplier": mods.dcv_multiplier,
        "dc_penalty": mods.dc_penalty,
        "hurried": fast,
    })


@resolves("climb")
def _resolve_climb(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Climb at the ordinary rate."""
    return _climb(session, actor, action, fast=False)


@resolves("climb_fast")
def _resolve_climb_fast(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """Climb faster, for a worse roll."""
    return _climb(session, actor, action, fast=True)


#: The interaction skills 6E1 p.60 makes Skill-vs-Skill contests. Kept as a
#: set rather than four near-identical resolvers, because the RULE is the
#: same for all of them and only the Skill named changes.
INTERACTION_SKILLS = ("charm", "persuasion", "conversation", "trading")


@resolves(*INTERACTION_SKILLS)
def _resolve_interaction(
    session: "CombatSession", actor, action: LegalAction, *,
    template: "CombatTemplate", roller,
) -> ResolvedAction:
    """An interaction skill used in combat --- Charm, Persuasion,
    Conversation, Trading.

    THE FOURTH RULE WITH NO ENGINE HOME. Sub-project B named four: trip,
    disarm, spread and interaction. The first three were wired earlier;
    this is the last, and it was invisible to the count because
    enumeration builds these four offers from a loop variable rather than
    a literal.

    A Skill Roll (6E1 p.58: 9 + CHAR/5) against the target's EGO-based
    resistance. The margin is what matters --- how much you talked them
    round --- so the payload carries it rather than a bare success flag.
    """
    target = session.combatants[action.target_id]
    stats, target_stats = actor.combat_stats(), target.combat_stats()

    #: Interaction Skills are PRE-based (6E1 p.60).
    skill_target = 9 + int(stats.pre) // 5
    #: The target resists with EGO, the characteristic that says how hard
    #: they are to talk into anything.
    resist = 9 + int(target_stats.ego) // 5
    roll = sum(roller.roll_dice(3))
    margin = skill_target - roll

    return _recorded(session, actor, action, margin, {
        "kind": action.kind,
        "target_id": target.id,
        "skill_target": skill_target,
        "resistance": resist,
        "roll": roll,
        "margin": margin,
        "succeeded": roll <= skill_target and margin >= (resist - skill_target),
    })
