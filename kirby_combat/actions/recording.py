"""Session-aware wrappers around pure action resolvers (attack, Block).

``AttackAction.resolve`` (and the ``resolve_attack`` dispatcher in
``actions/__init__.py``) is a pure calculator: a total function of its
inputs with no session coupling, which is exactly what makes it trivial
to test and safe to call from anywhere. That purity is an asset and is
left untouched here.

The gap it leaves is that nothing ever records the outcome anywhere —
callers that DO have a session (and want the attack's effects on the
event log) had no session-aware entry point to call, so kirby-api grew
its own ``ActionResolved`` construction instead
(its own resolution emitter). This module adds that entry point
inside kirby-combat, following the same shape already used by
``Flash.apply`` (``actions/flash.py``) and ``Grab.declare_and_resolve``
(``actions/grab.py``): run the pure calculation, then emit the event(s)
that describe it.

This lives in its own module (rather than being folded into
``actions/base.py``) because it is a different kind of thing from the
pipeline in that file: ``base.py`` holds pure, session-free resolution
logic shared by the concrete attack action classes, while this module is
glue between that pure core and the event-sourced ``CombatSession``. Its
only reason to import ``CombatSession``/``apply_event``/``ActionResolved``
at all is to record — mixing that into ``base.py`` would put session
plumbing in the one place the brief explicitly wants kept pure.

Opt-in only: existing callers of ``resolve_attack`` / ``AttackAction.resolve``
are completely unaffected — nothing here changes their behaviour, and
nothing here emits anything on their behalf. A caller must choose to call
``resolve_attack_in_session`` instead, which is what keeps this from
double-logging against kirby-api's own emission.

``resolve_block_in_session`` (below) does the same thing for
``Block.resolve`` (``actions/reactive/block.py``): that resolver is also a
pure calculator, so a Block's outcome never reached the event log, and
``Block.acts_first_priority`` (6E2 p.60, "ACTING FIRST") had no live
caller anywhere. See that function's docstring for the ``kind`` value it
chose and the limits of what it wires versus what it returns for a caller
to wire further.
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from dataclasses import replace as _replace
from datetime import datetime, timezone
from typing import Any, Literal, get_args

from kirby_combat.actions import resolve_attack
from kirby_combat.adjustments import adjusted_con, net_adjustment
from kirby_combat.actions.reactive.abort import mark_aborting
from kirby_combat.actions.reactive.block import Block, BlockResult
from kirby_combat.mental.mental_blast import MentalBlastResult, resolve_mental_blast
from kirby_combat.models import AttackInput, AttackResult, StatBlockCombatant
from kirby_combat.resolution.status import determine_status_changes
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_combatant,
)
from kirby_combat.template import CombatTemplate
from kirby_combat.vitals import apply_vitals_delta

#: The only ``action_type``/payload ``"kind"`` values kirby-api's own filter
#: accepts (``situation_builder.py:687-688``: ``kind not in ("attack",
#: "strike", "grab")``). Anything else is silently dropped by that filter,
#: not rejected as an error -- see ``resolve_attack_in_session``'s inline
#: comment on ``result_payload["kind"]``. Kept as a runtime tuple (not just
#: a type-checker-only ``Literal``) so a caller can assert against it
#: directly, e.g. ``assert "haymaker" not in ACCEPTED_ACTION_KINDS``.
ACCEPTED_ACTION_KINDS: tuple[str, ...] = get_args(
    Literal["attack", "strike", "grab"]
)
ActionKind = Literal["attack", "strike", "grab"]


def _apply_damage(session: CombatSession, target_id: str, *, stun: int, body: int) -> CombatSession:
    """Fold an attack's damage onto the session's own combatant for
    ``target_id``, returning a new session.

    MUTATE-THEN-LOG, NOT APPLY-TIME. ``session/apply.py`` deliberately
    treats ``ActionResolved`` as log-only: "combatant stat mutations in
    apply would force log replay to mirror combatant state, which is more
    brittle." So damage is applied here, beside the resolution, exactly as
    ``encounter.py``'s ``_apply_post_12_recovery`` applies Recovery and
    ``actions/movement/base.py``'s ``MovementAction.resolve`` applies an END
    spend ("apply_event won't do it for us"). Rewind and log replay are
    untouched by this.

    THE SESSION'S COMBATANT, NOT THE CALLER'S. The caller passes an
    ``AttackInput`` holding a combatant object that may be a stale copy
    taken before an earlier exchange in the same fight. Damage folds onto
    ``session.combatants[target_id]`` so successive attacks accumulate;
    resolving against the caller's handle would silently compute every hit
    after the first against a combatant that never took the previous one.

    A ``target_id`` the session does not know is a caller bug — it means
    the attack and the session disagree about who is in the fight — so it
    raises rather than no-opping, which would look exactly like a miss.
    """
    if target_id not in session.combatants:
        raise KeyError(
            f"target {target_id!r} is not a combatant in session {session.id!r}; "
            f"known combatants: {sorted(session.combatants)}"
        )
    if stun == 0 and body == 0:
        return session
    new_combatants = dict(session.combatants)
    new_combatants[target_id] = apply_vitals_delta(
        session.combatants[target_id], stun=-stun, body=-body,
    )
    return replace(session, combatants=new_combatants)


def _spend_attack_end(session: CombatSession, attacker_id: str, cost: int) -> CombatSession:
    """Take an attack's END off the attacker.

    Clamped at zero. HERO's rule for acting without the END to pay (take
    STUN instead) is NOT implemented and is not claimed to be; this only
    refuses to record a negative pool.

    An attacker the session does not know is not an error here the way a
    missing TARGET is: pure resolution is routinely handed a combatant
    object rather than a session member, and charging nobody is the safe
    reading.
    """
    if cost <= 0:
        return session
    combatant = session.combatants.get(attacker_id)
    if combatant is None:
        return session
    have = int(getattr(combatant.state, "current_end", 0) or 0)
    spend = min(cost, max(0, have))
    if spend <= 0:
        return session
    new_combatants = dict(session.combatants)
    new_combatants[attacker_id] = apply_vitals_delta(combatant, end=-spend)
    return replace(session, combatants=new_combatants)


def _cover_against(session: CombatSession, attack: AttackInput) -> tuple[int, int]:
    """Cover the TARGET enjoys against THIS attacker, and its OCV cost.

    Per shooter-target pair, which is the only way cover means anything:
    a barrel shields you from the man in front of it and not from the one
    who walked around it. `compute_cover_level` was already written that
    way; nothing had asked it.

    Returns (0, 0) whenever the question does not arise --- no scene, no
    map positions, either party unplaced. Most fights and nearly every
    test are on no map at all, and that must stay free rather than raise.
    """
    scene = getattr(session, "scene", None)
    if scene is None:
        return 0, 0
    positions = getattr(scene, "combatant_positions", None) or {}
    shooter = positions.get(attack.attacker.id)
    target = positions.get(attack.target.id)
    if shooter is None or target is None:
        return 0, 0

    from kirby_combat.scene.cover import compute_cover_level, cover_ocv_modifier
    from kirby_combat.statuses import statuses_for

    prone = "prone" in {
        str(s).lower() for s in (statuses_for(session, attack.target.id) or [])
    }
    level = compute_cover_level(
        shooter_pos=shooter, target_pos=target,
        target_is_prone_or_diving=prone, scene=scene,
    )
    return level, cover_ocv_modifier(level * 25)


def resolve_attack_in_session(
    session: CombatSession,
    attack: AttackInput,
    template: CombatTemplate,
    *,
    declaration_event_id: str | None = None,
    action_type: ActionKind = "attack",
) -> tuple[CombatSession, AttackResult]:
    """Resolve an attack and record the outcome on the session's event log.

    Runs the pure ``resolve_attack`` calculation unchanged, then emits an
    ``ActionResolved`` carrying the outcome — most importantly
    ``status_changes``, which the pure resolver computes
    (``AttackAction.resolve``, via ``determine_status_changes``) but has no
    session to hand it to, so today it is discarded by every caller that
    doesn't hand-roll its own recording.

    If ``declaration_event_id`` is omitted, an ``ActionDeclared`` is emitted
    first (mirroring ``Flash.apply`` / ``Grab.declare_and_resolve``) and its
    id is used as the resolution's ``declaration_event_id``. Pass an existing
    id when the caller already declared the action itself.

    Returns ``(new_session, result)`` — ``result`` is exactly what
    ``resolve_attack`` returned; nothing about the pure result is altered.
    """
    from kirby_combat.pre_attacks.violence import presence_from_violence
    from kirby_combat.session.apply import apply_event

    # COVER REACHES THE ROLL HERE, and only here.
    #
    # `resolve_attack` is pure and holds no scene; it takes an
    # `ocv_modifier` and applies it. The session is what holds the scene.
    # So the penalty is computed at this seam and folded into the input,
    # which keeps the pure resolver pure and gets every caller that goes
    # through the session --- a single attack, each shot of a Multiple
    # Attack, move-and-strike --- without any of them knowing about it.
    #
    # Before this, `compute_cover_level` had exactly one caller, `brief.py`,
    # which WRITES ABOUT the fight. Cover was scenery: a fighter who took
    # it gained nothing, and every tactic that valued cover valued zero.
    cover_level, cover_ocv = _cover_against(session, attack)
    if cover_ocv:
        attack = replace(attack, ocv_modifier=attack.ocv_modifier + cover_ocv)

    result = resolve_attack(attack, template)

    attacker_id = attack.attacker.id
    target_id = attack.target.id
    now = datetime.now(timezone.utc)

    # Apply the damage to the session's combatants, THEN log it -- the
    # two-step `_apply_post_12_recovery` and `MovementAction.resolve`
    # already use. See `_apply_damage` for why not in `apply_event`.
    s = _apply_damage(
        session, target_id, stun=result.stun_dealt, body=result.body_dealt,
    )

    # AND THE ATTACKER PAYS FOR IT. `result.end_spent` has been computed
    # and returned since attacks existed, and nothing ever subtracted it:
    # a fighter threw an 8d6 Blast and finished the Phase at the END he
    # started with, in an engine that implements Recovery, Post-Segment 12
    # Recovery and a REC characteristic with nothing to recover from.
    #
    # 6E1 p.132 prices it; `kirby_combat.endurance` computes it, and a
    # power on Charges or with Reduced Endurance (0 END) comes back 0, so
    # a gunfight full of charged revolvers still costs nobody anything.
    #
    # Folded here beside the damage for the same reason: `apply_event`
    # deliberately treats `ActionResolved` as log-only.
    s = _spend_attack_end(s, attack.attacker.id, int(result.end_spent or 0))

    # STUNNING AGAINST A DRAINED CON. `AttackAction.resolve` is a pure
    # resolver with no session, so it read the build's CON and could not
    # know about an Adjustment. Rather than thread a session into it --
    # which would stop it being pure -- the SAME rule function is asked
    # again with the adjusted value, and only when an Adjustment is
    # actually live, so the ordinary path is untouched.
    status_changes = list(result.status_changes)
    con_delta = net_adjustment(s, target_id, "CON")
    if con_delta:
        target_after = s.combatants[target_id]
        status_changes = determine_status_changes(
            stun_before=attack.target.current_stun,
            stun_after=target_after.state.current_stun,
            body_before=attack.target.current_body,
            body_after=target_after.state.current_body,
            con=adjusted_con(s, attack.target),
            max_body=attack.target.max_body,
        )
        # The RETURNED result carries the corrected status too. Leaving it
        # stale would put a different answer in `result.status_changes` than
        # in the payload `statuses_for` folds -- and a consumer reading the
        # result would be told a Drained target was not Stunned while the
        # log said otherwise. This is not "altering the pure calculation":
        # it is correcting an INPUT the pure resolver could not see, using
        # the same rule function it used.
        result = _replace(result, status_changes=status_changes)
    decl_id = declaration_event_id
    if decl_id is None:
        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=s.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id,
            action_type=action_type,
            targets=[target_id],
            parameters={"power_xmlid": attack.power.xmlid},
        )
        s = apply_event(s, declared)
        decl_id = declared.id

    # Established payload keys, matched to what kirby-api's own
    # resolution-emitting construction already writes: it reads "hit",
    # "stun_dealt" and "body_dealt" out of this payload in its rendering
    # and narration paths. "status_changes" is new: nothing persists it
    # today even though the consumer checks `result.status_changes` for
    # "Stunned" in six separate places, re-deriving it every request
    # because it was never recorded. "Knocked
    # Out" is one of the strings `determine_status_changes` may return
    # (kirby_combat/resolution/status.py), so it is already carried inside
    # status_changes rather than duplicated as a separate boolean key.
    # "kind" is required, not decorative: situation_builder.py:687-688 does
    # `kind = result.get("kind")` then filters on
    # `kind not in ("attack", "strike", "grab")` -- exactly
    # `ACCEPTED_ACTION_KINDS` above -- and soliloquy.py:255 reads
    # `payload.get("kind") or "action"` for narration. A payload without it
    # is silently dropped by that filter (not an error — just invisible) and
    # narrated as the generic "action". Sourced from `action_type`, which
    # already defaults to "attack" and lets a caller pass "strike"/"grab"
    # where those are the accurate label. `action_type`'s ``ActionKind``
    # annotation constrains it to that same set at the type-checker level
    # (a plain `str` here previously let `action_type="haymaker"` reproduce
    # the silent-drop with every test green -- see review finding #3).
    result_payload: dict[str, Any] = {
        "kind": action_type,
        "hit": result.hit,
        "stun_dealt": result.stun_dealt,
        "body_dealt": result.body_dealt,
        "status_changes": status_changes,
        "power_xmlid": result.power_xmlid,
        # WHICH power, not what KIND of power. Doc Holliday's Shotgun and
        # his Colt Peacemaker are both RKA, so an ammunition count keyed on
        # xmlid would empty one gun by firing the other. Identity is an id.
        "power_source_id": getattr(attack.power, "source_id", None),
        "target_id": target_id,
        # WHY it was harder than the bare CVs suggest. A to-hit that moved
        # silently is indistinguishable from a bad roll, both to a reader
        # and to anything learning from the log.
        "cover_level": cover_level,
        "cover_ocv": cover_ocv,
        # WHEN it landed. Needed by anything that reasons about blows within
        # one Segment -- a coordinated strike pools its participants' STUN
        # against CON (6E2 p.46), and without this the pool cannot tell an
        # attack in THIS Segment from one three Segments ago.
        "segment": s.timeline.segment,
    }

    resolved = ActionResolved(
        id=str(uuid.uuid4()),
        session_id=s.id,
        sequence=len(s.event_log) + 1,
        timestamp=now,
        author=make_author_combatant(attacker_id),
        declaration_event_id=decl_id,
        result_payload=result_payload,
    )
    s = apply_event(s, resolved)

    # WHAT THE ONLOOKERS SAW. 6E2 p.138 prices a violent action as bonus
    # Presence dice, and the engine could always RESOLVE a Presence Attack
    # while being unable to notice one happening: only a declared
    # `presence_attack` action ever made one. So a fighter could tear a man
    # in half in front of six people and none of them blinked.
    #
    # Recorded AFTER the resolution, so the log reads in the order it
    # happened: the blow lands, then the lot reacts to it. A blow that got
    # no BODY through returns the session untouched, which keeps ordinary
    # fights ordinary -- seven revolvers on a hide they cannot break are
    # loud and not frightening.
    attacker = s.combatants.get(attacker_id)
    if attacker is not None:
        s = presence_from_violence(
            s, attacker=attacker, target_id=target_id,
            body_dealt=result.body_dealt,
            target_max_body=attack.target.max_body,
            target_body_after=s.combatants[target_id].state.current_body,
            roller=session.dice_roller,
        )

    return s, result


def resolve_mental_blast_in_session(
    session: CombatSession,
    attacker: StatBlockCombatant,
    target: StatBlockCombatant,
    damage_dice_values: list[int],
    *,
    declaration_event_id: str | None = None,
    action_type: str = "mental_blast",
) -> tuple[CombatSession, MentalBlastResult]:
    """Resolve a Mental Blast and record the outcome on the session's event log.

    Same gap as ``resolve_attack_in_session``, in the one attack family that
    wrapper doesn't cover: ``resolve_mental_blast`` (``mental/mental_blast.py``)
    is also a pure calculator, and it already computes ``target_stunned`` /
    ``target_ko`` (``mental_blast.py:44-45``) but has no session to hand them
    to, so every caller today discards them. This function is that missing
    session-aware entry point -- it runs the pure calculation UNCHANGED (see
    that function's docstring: it must stay a total function of its inputs)
    and then emits an ``ActionResolved`` carrying a ``status_changes`` list.

    Unlike ``AttackResult``, ``MentalBlastResult`` has no ``status_changes``
    field of its own (it exposes the two raw booleans instead), so this
    function builds that list itself -- via ``determine_status_changes``
    (``resolution/status.py``), the SAME function ``AttackAction.resolve``
    calls, so the strings landing in the payload
    (``"Stunned"`` / ``"Knocked Out"`` / ``"Dead"``) are byte-identical to
    the ones ``statuses.py``'s ``_is_stunned`` / ``_is_dead`` /
    ``_is_knocked_out_from_payload`` already fold out of an
    ``ActionResolved`` payload -- so ``statuses_for`` picks up a mental
    Stunned with no change to ``statuses.py`` at all.

    Mental Blast deals STUN only by default (6E1 p.249: "Mental Blasts only
    do STUN damage, have no effect on inanimate objects, and do no
    Knockback" -- ``MentalBlastResult.body_dealt`` is hard-coded to 0 in
    the pure resolver accordingly, ``mental/mental_blast.py:37``), so
    ``body_before`` and ``body_after`` are passed through unchanged below
    -- ``determine_status_changes``'s ``"Dead"`` branch (``body_after <=
    -max_body``) can therefore never fire from a Mental Blast as this
    resolver is built today.

    6E2 p.106, "STUNNING": "If the STUN done to a character by a single
    attack (after subtracting defenses) exceeds his CON, he's Stunned...
    A Stunned character's DCV and DMCV instantly drop to ½." The rule is
    stated generically for STUN dealt by a single attack and calls out
    DMCV by name, so it applies to Mental Blast exactly as it does to a
    physical attack -- ``determine_status_changes``'s ``stun_dealt > con``
    check (the same "exceeds", not "meets or exceeds") is reused unmodified.

    If ``declaration_event_id`` is omitted, an ``ActionDeclared`` is emitted
    first (mirroring ``resolve_attack_in_session``) and its id is used as
    the resolution's ``declaration_event_id``. Pass an existing id when the
    caller already declared the action itself.

    ``kind`` defaults to ``"mental_blast"`` -- deliberately NOT one of
    ``ACCEPTED_ACTION_KINDS`` (kirby-api's attack filter,
    ``situation_builder.py:687-688``, only recognizes "attack"/"strike"/
    "grab"): a Mental Blast is none of those, and mislabeling it as one to
    slip past that filter would misdescribe it to any consumer that reads
    ``kind`` for narration. Widening that filter to also accept
    "mental_blast" is kirby-api's call, out of scope here (see
    ``resolve_block_in_session``'s docstring for the same reasoning applied
    to ``"block"``).

    Returns ``(new_session, result)`` -- ``result`` is exactly what
    ``resolve_mental_blast`` returned; nothing about the pure result is
    altered.
    """
    from kirby_combat.session.apply import apply_event

    result = resolve_mental_blast(attacker, target, damage_dice_values)

    attacker_id = attacker.id
    target_id = target.id
    now = datetime.now(timezone.utc)

    # Apply the damage to the session's combatants, THEN log it -- the
    # two-step `_apply_post_12_recovery` and `MovementAction.resolve`
    # already use. See `_apply_damage` for why not in `apply_event`.
    s = _apply_damage(
        session, target_id, stun=result.stun_dealt, body=result.body_dealt,
    )
    decl_id = declaration_event_id
    if decl_id is None:
        declared = ActionDeclared(
            id=str(uuid.uuid4()),
            session_id=s.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id,
            action_type=action_type,
            targets=[target_id],
            parameters={},
        )
        s = apply_event(s, declared)
        decl_id = declared.id

    status_changes = determine_status_changes(
        stun_before=target.current_stun,
        stun_after=target.current_stun - result.stun_dealt,
        body_before=target.current_body,
        body_after=target.current_body,
        # Drained CON is one of the sharpest things an Adjustment does:
        # Stunning is "STUN exceeds his CON", so lowering CON makes a target
        # easier to Stun with blows that would otherwise fall short.
        con=adjusted_con(s, target),
        max_body=target.max_body,
    )

    result_payload: dict[str, Any] = {
        "kind": action_type,
        "stun_dealt": result.stun_dealt,
        "body_dealt": result.body_dealt,
        "status_changes": status_changes,
        "target_id": target_id,
    }

    resolved = ActionResolved(
        id=str(uuid.uuid4()),
        session_id=s.id,
        sequence=len(s.event_log) + 1,
        timestamp=now,
        author=make_author_combatant(attacker_id),
        declaration_event_id=decl_id,
        result_payload=result_payload,
    )
    s = apply_event(s, resolved)

    return s, result


def resolve_block_in_session(
    session: CombatSession,
    *,
    blocker_id: str,
    attacker_id: str,
    blocker_ocv: int,
    blocker_dice: list[int],
    attacker_ocv: int,
    declaration_event_id: str | None = None,
) -> tuple[CombatSession, BlockResult, dict[str, str]]:
    """Resolve a Block and record the outcome on the session's event log.

    Runs the pure ``Block.resolve`` calculation unchanged (``actions/
    reactive/block.py``), then emits an ``ActionResolved`` carrying the
    outcome — the same gap ``resolve_attack_in_session`` closes for
    attacks: ``Block.resolve`` is a pure calculator with no session, so
    nothing recorded a Block's outcome anywhere before this.

    If ``declaration_event_id`` is omitted, this calls ``mark_aborting``
    (``actions/reactive/abort.py``) to emit the ``AbortDeclared`` Block
    already declares itself with via ``Block.declare`` (which is exactly
    ``mark_aborting(session, combatant_id, to_action="block")``) -- and by
    doing so on this default path, THIS function is now a caller feeding
    ``session.timeline.aborted_this_phase``, a ONE-WAY LATCH that nothing
    in this package ever clears (``statuses.py``'s ``ABORTED`` comment:
    "aborted for the rest of the fight", not "aborted this phase") -- and uses
    its id as the resolution's ``declaration_event_id``. Pass the id
    ``Block.declare`` already returned when the caller declared the Block
    itself; this parameter exists so callers who separate declare/resolve
    across a Segment boundary (the normal case for a reactive defense)
    don't get a second, spurious ``AbortDeclared``.

    ``kind`` on the payload is ``"block"`` — a deliberate, distinct value,
    not one of the three kirby-api's attack filter accepts (`kind not in
    ("attack", "strike", "grab")` at situation_builder.py:687-688). A
    Block is not an attack, a strike, or a grab, and mislabeling it as one
    of those to slip past that filter would be worse than the filter
    simply not recognizing it yet: extending kirby-api's filter to also
    accept "block" is kirby-api's call, out of scope here.

    ``Block.acts_first_priority`` (6E2 p.60, "ACTING FIRST") had no live
    caller anywhere in kirby_combat before this. This function is that
    caller: it computes the priority mapping from the just-resolved
    ``BlockResult`` and returns it as the third tuple element — `{}` on a
    failed Block, `{blocker_id: attacker_id}` on a successful one — so a
    caller that owns an ``Encounter`` can merge it into
    ``Encounter.acts_first`` itself (via ``dataclasses.replace``, since
    ``Encounter`` is immutable). This function does not reach into
    ``Encounter.acts_first`` itself: doing so needs a driver that holds
    both a ``CombatSession`` and its ``Encounter`` together, and no such
    driver exists in kirby_combat today (nor does this task touch
    ``encounter.py`` to add one) — leaving that merge to the returned
    value is the honest state of the wiring, not a half-connected guard
    that looks wired and isn't.

    Returns ``(new_session, result, acts_first_priority)`` — ``result`` is
    exactly what ``Block.resolve`` returned; nothing about the pure result
    is altered.
    """
    from kirby_combat.session.apply import apply_event

    result = Block.resolve(
        blocker_ocv=blocker_ocv, blocker_dice=blocker_dice,
        attacker_ocv=attacker_ocv,
    )

    now = datetime.now(timezone.utc)

    s = session
    decl_id = declaration_event_id
    if decl_id is None:
        s, declared = mark_aborting(s, blocker_id, to_action="block")
        decl_id = declared.id

    result_payload: dict[str, Any] = {
        "kind": "block",
        "success": result.success,
        "blocker_id": blocker_id,
        "attacker_id": attacker_id,
        "blocker_roll": result.blocker_roll,
        "blocker_margin": result.blocker_margin,
        "attacker_ocv": result.attacker_ocv,
        "blocker_ocv": result.blocker_ocv,
    }

    resolved = ActionResolved(
        id=str(uuid.uuid4()),
        session_id=s.id,
        sequence=len(s.event_log) + 1,
        timestamp=now,
        author=make_author_combatant(blocker_id),
        declaration_event_id=decl_id,
        result_payload=result_payload,
    )
    s = apply_event(s, resolved)

    priority = Block.acts_first_priority(result, blocker_id, attacker_id)

    return s, result, priority


__all__ = [
    "resolve_attack_in_session",
    "resolve_mental_blast_in_session",
    "resolve_block_in_session",
    "ACCEPTED_ACTION_KINDS",
    "ActionKind",
]
