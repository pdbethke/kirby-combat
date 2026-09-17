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


def _tracks_endurance(template, attacker) -> bool:
    """Whether this campaign counts END at all.

    THE TEMPLATES HAVE SAID THIS SINCE THEY WERE WRITTEN and nothing read
    them: `RAW_SUPERHEROIC` ships `manage_endurance=False` ("END
    optional"), `RAW_HEROIC` ships `manage_endurance=True` ("grittier; hit
    locations and END tracked"). That is the genre split -- four-colour
    games hand-wave END, gritty ones count it -- and charging END
    unconditionally quietly overrode a policy the data already stated.

    `manage_endurance_npc` is the second half of the same pair, and
    `StatBlockCombatant.is_npc` was likewise read by nothing: a table that
    tracks END for the player characters and not for the mooks is an
    ordinary house rule, and both fields exist to express it.
    """
    if template is None:
        return True
    if getattr(attacker, "is_npc", False):
        return bool(getattr(template, "manage_endurance_npc", False))
    return bool(getattr(template, "manage_endurance", False))


def _spend_attack_end(session: CombatSession, attacker, cost: int,
                      template) -> CombatSession:
    """Take an attack's END off the attacker, when the campaign counts it.

    Clamped at zero. HERO's rule for acting without the END to pay (take
    STUN instead) is NOT implemented and is not claimed to be; this only
    refuses to record a negative pool.

    An attacker the session does not know is not an error here the way a
    missing TARGET is: pure resolution is routinely handed a combatant
    object rather than a session member, and charging nobody is the safe
    reading.
    """
    if cost <= 0 or not _tracks_endurance(template, attacker):
        return session
    combatant = session.combatants.get(getattr(attacker, "id", None))
    if combatant is None:
        return session
    have = int(getattr(combatant.state, "current_end", 0) or 0)
    spend = min(cost, max(0, have))
    if spend <= 0:
        return session
    new_combatants = dict(session.combatants)
    new_combatants[combatant.id] = apply_vitals_delta(combatant, end=-spend)
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


def _surprise_for(session: CombatSession, actor, target):
    """6E2 p.52's Surprised for this attack, or None when it cannot apply.

    Moved here from `loop/resolvers.py` with the rest of the per-fight CV
    rules: it was asked by the plain-attack resolver and by none of the
    other six callers that reach this module, so a move-and-strike or a
    rapid-fire burst out of the dark surprised nobody.

    `perception.is_surprised` has answered the perception half since the
    perception line shipped and its docstring said the rest "is applied by
    the driver, which knows the combat clock". The attacker's concealment
    comes from `concealment`, which reads the fight's own log -- a
    successful Hide recorded who lost track of whom.

    NOT GEOMETRY. p.52 refuses the positional reading outright: moving
    behind a man who can see you "does not per se earn an attacker a
    Surprised bonus". So no angle is computed here, and none should be.
    """
    from kirby_combat.concealment import concealment_for
    from kirby_combat.perception import is_surprised
    from kirby_combat.resolution.surprise import surprise_for

    scene = getattr(session, "scene", None)
    if scene is None:
        return None                     # no map, no senses to model
    conceal = concealment_for(session, observer_id=getattr(target, "id", ""))
    invisible, hidden = conceal.get(getattr(actor, "id", ""), (False, False))

    # A RECORDED HIDE IS NOT RE-LITIGATED. `_resolve_hide` already ran the
    # contest -- Stealth against this watcher's PER, this Phase -- and the
    # log says he lost. `perceive` would run a SECOND contest with
    # different terms, and asking twice means the hider must win twice.
    if hidden:
        return surprise_for(target=target, perceives_attacker=False)

    try:
        blind = is_surprised(
            observer=target, attacker=actor, scene=scene,
            attacker_invisible=invisible, attacker_hidden=hidden,
        )
    except Exception:
        return None                     # fail OPEN: never invent a surprise
    return surprise_for(target=target, perceives_attacker=not blind)


def _activation_check(session: CombatSession, attack: AttackInput, roller):
    """6E1 p.375's Activation Roll for this attack, or None if it has none.

    Returns ``{"activated": bool, "roll": int, "target": int}``. None ---
    not a dict saying "activated" --- when the power was not bought with an
    Activation Roll at all, so a caller can tell "made it" from "never had
    to make one" and the log can say which.

    AT THIS DOOR, not in one resolver. It lived in `loop/resolvers.py`'s
    plain-attack path for a day, which meant a Pushed blast, a thrown
    wagon, a move-and-strike and every shot of a rapid-fire burst fired an
    unreliable power with no roll at all.

    NOTHING IS ROLLED WHEN THERE IS NO ROLL TO MAKE. A power with no
    Activation Roll draws no dice, which keeps ONE dice sequence per seed:
    charging every attack in the engine a 3d6 it does not need would have
    moved every seeded fight this suite and the benchmarks depend on.

    WHERE IT FALLS IN THE SEQUENCE: after the attack's own dice, not
    before. Every caller builds its `DiceValues` while assembling the
    `AttackInput`, so by the time the door is reached the to-hit, damage,
    location and STUN-multiplier dice have been drawn. Those dice are drawn
    unconditionally either way, so the sequence is the same for a given
    seed whether the power activates or not -- which is the property that
    matters. Rolling the Activation first would mean moving dice assembly
    to this door, a larger change than the rule needs.

    The roller is the CALLER's when it has one --- a resolver holding the
    Phase's roller passes it, so a seeded fight stays seeded --- and
    `session.dice_roller` otherwise, which is the roller this module
    already uses for a Presence Attack.
    """
    target = getattr(attack.power, "activation_roll", None)
    if target is None:
        return None
    rolled = sum((roller or session.dice_roller).roll_dice(3))
    return {"activated": rolled <= int(target), "roll": rolled,
            "target": int(target)}


def _record_failed_activation(
    session: CombatSession, attack: AttackInput, activation: dict, *,
    declaration_event_id: str | None, action_type: str,
) -> tuple[CombatSession, AttackResult]:
    """Log an attack whose power never went off, and return a null result.

    A FAILURE IS RECORDED, NOT SWALLOWED. An attack that vanished with no
    row on the log is indistinguishable from one that was never declared
    --- to a reader, to a narrator, and to anything learning from the
    fight. It keeps ``kind`` from `action_type`, because that is what every
    downstream filter and narrator reads.

    ``to_hit`` is None on the returned result and the three CV keys are
    stamped None on the payload, so every attack row has ONE shape: a
    consumer reads `effective_ocv` on every resolution and gets a number or
    an explicit "there was no roll", never a missing key. `_maybe_stray`
    already guards on `to_hit is None` --- a shot that was never fired
    cannot stray into the man behind.

    JUDGEMENT, labelled: a failed Activation costs no END and spends no
    Charge. No power was used; `endurance.py` prices a power's END for
    using it and `charges.py` counts a firing off the log, which this
    payload deliberately carries no `power_source_id` to be counted as.
    The books' treatment of both on a failed Activation is not settled in
    front of this function, so the cheap reading is taken and named rather
    than asserted as RAW.
    """
    from kirby_combat.session.apply import apply_event

    now = datetime.now(timezone.utc)
    attacker_id = attack.attacker.id
    target_id = attack.target.id
    s = session
    decl_id = declaration_event_id
    if decl_id is None:
        declared = ActionDeclared(
            id=str(uuid.uuid4()), session_id=s.id,
            sequence=len(s.event_log) + 1, timestamp=now,
            author=make_author_combatant(attacker_id),
            combatant_id=attacker_id, action_type=action_type,
            targets=[target_id],
            parameters={"power_xmlid": attack.power.xmlid},
        )
        s = apply_event(s, declared)
        decl_id = declared.id

    resolved = ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id,
        sequence=len(s.event_log) + 1, timestamp=now,
        author=make_author_combatant(attacker_id),
        declaration_event_id=decl_id,
        result_payload={
            "kind": action_type,
            "hit": False,
            "stun_dealt": 0,
            "body_dealt": 0,
            "status_changes": [],
            "target_id": target_id,
            "power_xmlid": attack.power.xmlid,
            "power_name": getattr(attack.power, "name", None),
            "damage_type": getattr(attack.power, "damage_type", None),
            "is_ranged": bool(getattr(attack.power, "is_ranged", False)),
            "segment": s.timeline.segment,
            # ONE SHAPE for every attack row. There was no roll, and the
            # keys say so rather than going missing.
            "effective_ocv": None,
            "target_dcv": None,
            "margin": None,
            "activated": False,
            "activation_roll": activation["roll"],
            "activation_target": activation["target"],
        },
    )
    s = apply_event(s, resolved)
    return s, AttackResult(
        hit=False, to_hit=None, damage=None, defense=None,
        stun_dealt=0, body_dealt=0, end_spent=0, knockback=None,
        status_changes=[], power_xmlid=attack.power.xmlid,
        audit_trail=[
            f"Activation Roll (6E1 p375): {activation['roll']} vs "
            f"{activation['target']}- — the power does not go off"
        ],
    )


def _fold_session_cvs(
    session: CombatSession, attack: AttackInput, combat_type: str | None = None,
) -> AttackInput:
    """Fold every per-fight condition onto this attack's two CVs.

    **THE ONE DOOR.** These rules -- 6E2 p.127's blind penalty, p.55's
    Dodge, 6E1 p.139's Drained CV, p.52's Surprised, and through
    `cv_modifiers` also p.106's Stunned and the multiple-attack penalty --
    were applied by the plain-attack resolver and by NONE of the other six
    callers that reach this module. `_reposition(then_attack=True)`,
    `_resolve_shots` (rapid fire, multiple attack, sweep), `_resolve_throw`,
    `_resolve_push` and `_maybe_stray` each assembled their own
    `AttackInput` and got none of it, so a man in a Darkness field was
    blind to a punch and sighted to a move-and-strike. That is this
    engine's dominant defect shape -- a rule at one door and not the others
    -- and the fix is not six more copies. It is this function, on the
    path every one of them already takes.

    **ONE FOLD FOR THE ADJUSTMENTS, and it is `cv_modifiers`'.**
    `effective_ocv_for` / `effective_dcv_for` already compose the
    Adjustment (applied to the BASE, before any factor, which is the
    ordering 6E1 p.133/p.139 requires), Stunned, a landed Presence Attack,
    the multiple-attack penalty and 6E2 p.9's per-opponent sense row -- and
    had no caller in the package. A second fold lived here for a week;
    it is deleted. The result comes back as a DELTA on the existing
    `ocv_modifier` / `dcv_modifier` channel, so `resolution/to_hit.py` is
    untouched and a caller that set its own modifier keeps it.

    **JUDGEMENT: the DCV is halved ONCE.** 6E2 p.52's Surprised and 6E2
    p.9's inability to sense both halve a defender, and on this path they
    usually have the same cause -- `_surprise_for` and `cannot_perceive`
    ask the same perception question. A man in the dark would otherwise go
    DCV 5 -> 3 -> 2 for one fact stated on two pages. So when a Surprise is
    live, the p.9 row's FACTOR is left out of his DCV and its flat delta is
    not: p.9's mitigated hand-to-hand row is a -1 DCV rather than a
    halving, it is a different penalty for a different reason (he made a
    Nontargeting PER Roll), and dropping it with the halving would have
    been a second, quieter error. This halve-once reading is a JUDGEMENT,
    not a cited rule: no page says the two do not stack.

    A combatant the session does not know is left alone entirely. Pure
    resolution is routinely handed a combatant object rather than a session
    member, and folding a fight's conditions onto a stranger is not
    something this function can do honestly.
    """
    from kirby_combat.actions.reactive.dodge import Dodge
    from kirby_combat.cv_modifiers import (
        apply_cv_delta, effective_dcv_for, effective_ocv_for,
    )
    from kirby_combat.sense_penalties import HTH, RANGED, sense_penalty_modifiers

    attacker_id = getattr(attack.attacker, "id", None)
    target_id = getattr(attack.target, "id", None)
    if attacker_id not in session.combatants or target_id not in session.combatants:
        return attack

    # 6E2 p.9's two rows. `is_ranged` is the field `AttackPower` already
    # derives from the power's range and that `_is_melee` already reads;
    # asking it here keeps ONE answer to "is this a shot or a punch".
    # ``combat_type`` is derived from the power unless the CALLER knows
    # better. A maneuver does: Trip (6E2 p.67) and Disarm (p.65) are
    # hand-to-hand maneuvers whatever power the offer happened to carry as
    # its damage handle, and reading `is_ranged` off that handle would put
    # a man throwing a Trip on p.9's Ranged row -- OCV to ZERO instead of
    # halved, which is wrong by five and in the punishing direction.
    if combat_type is None:
        combat_type = RANGED if getattr(attack.power, "is_ranged", False) else HTH

    # A caller that decided the Surprise itself keeps it -- a GM override
    # and `resolution/surprise.py`'s own tests both do -- and everyone else
    # gets the answer the fight's log and senses give.
    surprise = attack.surprise
    if surprise is None:
        surprise = _surprise_for(session, attack.attacker, attack.target)

    base_ocv = int(session.combatants[attacker_id].combat_stats().ocv)
    ocv_delta = effective_ocv_for(
        session, attacker_id, against=target_id, combat_type=combat_type,
    ) - base_ocv

    base_dcv = int(session.combatants[target_id].combat_stats().dcv)
    if surprise:
        # The halve-once JUDGEMENT above: everything except p.9's
        # per-opponent row, plus that row's flat delta.
        effective = effective_dcv_for(session, target_id)
        row = sense_penalty_modifiers(
            session, target_id, attacker_id, combat_type,
        )
        effective = apply_cv_delta(effective, int(row.get("dcv_delta", 0)))
    else:
        effective = effective_dcv_for(
            session, target_id, against=attacker_id, combat_type=combat_type,
        )
    # 6E2 p.55: a Dodge is +3 DCV against all attacks this Phase.
    # `Dodge.dcv_bonus` had no production caller anywhere, so a fighter
    # gave up his next Phase for a bonus nothing read. Added here rather
    # than as a `cv_modifiers` source because it is a flat bonus a
    # combatant DECLARED, not a condition he is under.
    dcv_delta = (effective - base_dcv) + Dodge.dcv_bonus(session, target_id)

    return replace(
        attack,
        surprise=surprise,
        ocv_modifier=attack.ocv_modifier + ocv_delta,
        dcv_modifier=attack.dcv_modifier + dcv_delta,
    )


def resolve_attack_in_session(
    session: CombatSession,
    attack: AttackInput,
    template: CombatTemplate,
    *,
    declaration_event_id: str | None = None,
    action_type: ActionKind = "attack",
    extra_payload: dict[str, Any] | None = None,
    roller=None,
    combat_type: str | None = None,
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

    ``extra_payload`` is merged into the resolution payload: keys a CALLER
    knows and this function cannot, such as the Activation Roll (6E1 p.375)
    a resolver made before the attack was built. It is a parameter rather
    than a re-stamping pass over the log afterwards, because a second pass
    that hunts for the event it just wrote is the shape that had three
    keys reaching maneuvers and no other attack. It cannot overwrite a key
    this function computes; a caller that tries gets a ValueError rather
    than a payload whose `hit` disagrees with the result beside it.

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
    # EVERY PER-FIGHT CONDITION ON THE TWO CVs, at this one door. See
    # `_fold_session_cvs`: these rules reached the plain-attack resolver and
    # none of the other six callers that arrive here.
    # 6E1 p.375: does the power go off at all? Asked FIRST, because a power
    # that does not fire is never rolled to hit -- and asked HERE, so that
    # a thrown object, a Pushed blast and each shot of a rapid-fire burst
    # must make the roll the plain attack makes.
    activated = _activation_check(session, attack, roller)
    if activated is not None and not activated["activated"]:
        return _record_failed_activation(
            session, attack, activated,
            declaration_event_id=declaration_event_id,
            action_type=action_type,
        )

    # EVERY PER-FIGHT CONDITION ON THE TWO CVs, at this one door. See
    # `_fold_session_cvs`: these rules reached the plain-attack resolver and
    # none of the other six callers that arrive here.
    attack = _fold_session_cvs(session, attack, combat_type)

    cover_level, cover_ocv = _cover_against(session, attack)
    if cover_ocv:
        attack = replace(attack, ocv_modifier=attack.ocv_modifier + cover_ocv)
    # AND THE LEVEL ITSELF, not just its OCV cost. `_cover_against` has
    # computed a per shooter-target cover level since cover was wired and
    # only the penalty was ever used; a rolled Hit Location needs the
    # level to know whether the shot found the man or the barrel he is
    # behind (6E2 p.45).
    if cover_level:
        attack = replace(attack, target_cover_level=cover_level)

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
    s = _spend_attack_end(s, attack.attacker, int(result.end_spent or 0), template)

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
        # WHAT IT WAS, for anything narrating the blow. `power_xmlid` is a
        # TYPE and a coarse one -- a revolver, a crossbow and a laser are
        # all RKA -- so a reader that wants to say BLAM rather than POW
        # needs the weapon's name and its shape. Cheap, and the log is the
        # only place a replay can learn it: the renderer sees the event and
        # never the build.
        "power_name": getattr(attack.power, "name", None),
        "damage_type": getattr(attack.power, "damage_type", None),
        "is_ranged": bool(getattr(attack.power, "is_ranged", False)),
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
        # WHAT THE ROLL WAS ACTUALLY MADE AGAINST. Read off the engine's own
        # `ToHitResult` rather than recomputed -- `margin` is
        # `target_number - roll` and the resolver has already worked it out.
        #
        # STAMPED HERE, ONCE, because this is the one place every attack
        # goes through. A2 stamped these three keys from a helper
        # (`resolvers._report_cvs`) that ran only on the three maneuvers it
        # had just written, and found the event by scanning the log
        # backwards for a payload with a "hit" key -- so a plain attack, the
        # action most fights consist of, reported only whether it landed. A
        # blow halved for blindness and one that simply rolled badly were
        # the same row. The rule this engine keeps paying for is a rule at
        # one door and not the others; these are written at the door.
        "effective_ocv": result.to_hit.effective_ocv,
        "target_dcv": result.to_hit.effective_dcv,
        "margin": result.to_hit.margin,
    }

    if activated is not None:
        # The Activation Roll it MADE, in the same keys the failure writes.
        # Both answers on the log means a reader can tell "made it" from
        # "never had to make one" -- the whole reason `activation_roll` is
        # None rather than 0.
        result_payload.update({
            "activated": True,
            "activation_roll": activated["roll"],
            "activation_target": activated["target"],
        })

    if extra_payload:
        clash = sorted(set(extra_payload) & set(result_payload))
        if clash:
            raise ValueError(
                f"extra_payload would overwrite keys this resolver computes: "
                f"{clash}"
            )
        result_payload.update(extra_payload)

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
