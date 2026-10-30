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
from typing import Any, Callable, Literal, get_args

from kirby_combat.actions import resolve_attack
from kirby_combat.adjustments import adjusted_con, net_adjustment
from kirby_combat.actions.reactive.abort import mark_aborting
from kirby_combat.actions.reactive.block import Block, BlockResult
from kirby_combat.mental.mental_blast import MentalBlastResult, resolve_mental_blast
from kirby_combat.mental.mental_combat import MentalToHitResult
from kirby_combat.models import AttackInput, AttackResult, StatBlockCombatant
from kirby_combat.resolution.status import determine_status_changes
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, BlockPriorityGained,
    make_author_combatant,
)
from kirby_combat.template import CombatTemplate
from kirby_combat.vitals import record_vitals_change

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

    THROUGH THE LOG, NOT BESIDE IT. This used to fold the damage onto
    ``session.combatants`` and leave the recording to an
    ``ActionResolved`` whose ``result_payload`` is a free-form dict ---
    "mutate-then-log", the arrangement every resolver in the engine
    copied. Nothing in the rows made anybody's STUN move, so a consumer
    that rebuilt the fight by replaying them rebuilt a fight in which
    nobody had been hit. It emits a typed ``VitalsChanged`` now and
    ``apply_event`` does the writing; ``ActionResolved`` still carries
    the outcome (what was rolled, what got through, who was Stunned) and
    no fold has to parse it.

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
    session, _ = record_vitals_change(
        session, target_id, stun=-stun, body=-body, reason="damage",
    )
    return session


def _impact_stunned(landed: dict) -> bool:
    """Did a Knockback impact or a fall, on its own, beat his CON?

    Every impact is its own instance of damage (6E2 p.105), so each wall he
    went through counts, not only the one that stopped him or the ground."""
    kb = landed.get("knockback") or {}
    footing = landed.get("footing") or {}
    parts = [kb.get("impact"), kb.get("fall"), footing.get("fall"),
             *(w.get("impact") for w in kb.get("walls") or ())]
    return any(bool(p and p.get("stunned")) for p in parts)


def _tracks_endurance(template, attacker) -> bool:
    """See `kirby_combat.endurance.tracks_endurance`."""
    from kirby_combat.endurance import tracks_endurance

    return tracks_endurance(template, attacker)


def _spend_attack_end(session: CombatSession, attacker, cost: int,
                      template, *, power) -> CombatSession:
    """Take an attack's END off the attacker, when the campaign counts it.

    Clamped at zero. HERO's rule for acting without the END to pay (take
    STUN instead) is NOT implemented and is not claimed to be; this only
    refuses to record a negative pool. The clamp happens BEFORE the
    event, deliberately: `apply_vitals_delta` clamps nothing, so the
    number in the log has to be the number that was really taken, or a
    replay and the fight that ran would differ by whatever the clamp ate.
    (That is the END-clamp lesson from the earlier replay work, stated
    the other way round.)

    An attacker the session does not know is not an error here the way a
    missing TARGET is: pure resolution is routinely handed a combatant
    object rather than a session member, and charging nobody is the safe
    reading.

    THE SPEND IS IN THE LOG. It was folded onto the combatant and
    recorded nowhere at all, so a replayed fighter threw blasts for free.
    """
    from kirby_combat.endurance import pay_end

    combatant = session.combatants.get(getattr(attacker, "id", None))
    if combatant is None:
        return session
    # FROM THE POOL THE POWER DRAWS ON: his own END, or an Endurance
    # Reserve (6E1 p.207). ``power`` is required, so every spend says which;
    # None is a spend with no power behind it (STR, an EGO escape).
    return pay_end(session, combatant.id, cost, power=power, template=template)


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

    from kirby_world.cover import compute_cover_level, cover_ocv_modifier
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


def _record_blocked_attack(
    session: CombatSession, attack: AttackInput, template: CombatTemplate,
    block: BlockResult, *, declaration_event_id: str | None, action_type: str,
) -> tuple[CombatSession, AttackResult]:
    """Log an attack a Block stopped, and return a null result.

    6E2 p.59: the blocker "takes no damage (and no Knockdown or
    Knockback)". The attack WAS made, so it is declared and resolved like
    any other --- ``hit: False``, no damage, the Block's numbers beside it
    --- and the attacker pays its END and its Charge: he swung, and the
    swing was turned aside. ``to_hit`` is None and the three CV keys are
    None, the same "no roll that counts" shape `_record_failed_activation`
    writes, because the attacker's roll never decided anything.
    """
    from kirby_combat.session.apply import apply_event

    now = datetime.now(timezone.utc)
    attacker_id = attack.attacker.id
    target_id = attack.target.id
    # What the swing cost, from the same pure resolver every attack is
    # priced by; its dice were rolled into `attack.dice` already, so asking
    # draws nothing.
    end_spent = int(resolve_attack(attack, template).end_spent or 0)
    s = _spend_attack_end(session, attack.attacker, end_spent, template,
                          power=attack.power)
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
            "power_source_id": getattr(attack.power, "source_id", None),
            "power_name": getattr(attack.power, "name", None),
            "damage_type": getattr(attack.power, "damage_type", None),
            "is_ranged": bool(getattr(attack.power, "is_ranged", False)),
            "segment": s.timeline.segment,
            "effective_ocv": None,
            "target_dcv": None,
            "margin": None,
            "blocked": True,
            "blocker_roll": block.blocker_roll,
            "attacker_ocv": block.attacker_ocv,
            "blocker_ocv": block.blocker_ocv,
        },
    )
    s = apply_event(s, resolved)
    return s, AttackResult(
        hit=False, to_hit=None, damage=None, defense=None,
        stun_dealt=0, body_dealt=0, end_spent=end_spent, knockback=None,
        status_changes=[], power_xmlid=attack.power.xmlid,
        audit_trail=[
            f"Blocked (6E2 p59): {target_id} rolled {block.blocker_roll} "
            f"with OCV {block.blocker_ocv} against OCV {block.attacker_ocv} "
            "--- no damage, no Knockback"
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
    # And a standing Block's DCV: "The CV bonuses obtained from Block are
    # general ones; they apply against all characters" (6E2 p.59). +0 for
    # the plain maneuver, a Martial Block's +2 (6E2 p.93).
    from kirby_combat.actions.reactive.blocking import block_dcv_bonus

    dcv_delta = ((effective - base_dcv) + Dodge.dcv_bonus(session, target_id)
                 + block_dcv_bonus(session, target_id))
    # 6E2 p.68 / p.93: the DCV a martial maneuver left him at, until his
    # next Phase. A flat modifier he CHOSE, like the Dodge above, and read
    # here for the same reason: this is the one door every attack on him
    # takes.
    from kirby_combat.actions.martial_arts import maneuver_dcv_delta

    dcv_delta += maneuver_dcv_delta(session, target_id)

    # 6E2 p.49: from a difficult face he "subtract[s] 2 DCs from all
    # attacks". A condition of the ATTACKER's, on the DC channel the pure
    # resolver trims (`actions/base.py`). See `climbing_state`.
    from kirby_combat.climbing_state import climbing_dc_penalty

    return replace(
        attack,
        surprise=surprise,
        ocv_modifier=attack.ocv_modifier + ocv_delta,
        dcv_modifier=attack.dcv_modifier + dcv_delta,
        dc_modifier=attack.dc_modifier + climbing_dc_penalty(session, attacker_id),
    )


def resolve_attack_in_session(
    session: CombatSession,
    attack: AttackInput,
    template: CombatTemplate,
    *,
    declaration_event_id: str | None = None,
    action_type: ActionKind = "attack",
    roller=None,
    combat_type: str | None = None,
    payload_extras: "Callable[[AttackResult], dict[str, Any]] | None" = None,
    paid_use_event_id: str | None = None,
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

    ``payload_extras`` is how a MANEUVER labels the row it produces. It is
    called with the finished ``AttackResult`` and its return value is
    merged into ``result_payload`` BEFORE the ``ActionResolved`` is built
    --- so the row that is applied is the finished row. The Trip resolver
    used to reach into ``session.event_log[-1]`` after ``apply_event`` had
    committed it and ``dataclasses.replace`` the payload there, which a
    consumer persisting rows as they are emitted never sees: it stored the
    pre-edit payload, ``statuses._is_prone`` folded that, and the replayed
    fight had a man standing whom the live fight had prone. Nothing edits a
    committed row.

    ``paid_use_event_id`` marks an application that is part of a use
    already made and paid for elsewhere --- one victim of an Area Of Effect,
    one dose of a Constant or Damage Over Time attack. Such an application
    makes no Activation Roll, pays no END, and carries no
    ``power_source_id`` (so `charges.spent_charges` counts the use once):
    the use's own row did all three.

    THE SHAPE OF THE ATTACK IS DECIDED HERE TOO, for the same reason the
    CV folds are: every caller reaches this door. An Area Of Effect goes
    to `actions/area_attack.py`; a Damage Over Time use rolls to hit and
    does no damage until its first dose (`lingering.py`); a Constant hit
    starts being maintained; Side Effects land on the attacker.

    Returns ``(new_session, result)`` — ``result`` is exactly what
    ``resolve_attack`` returned; nothing about the pure result is altered.
    """
    from kirby_combat.pre_attacks.violence import presence_from_violence
    from kirby_combat.session.apply import apply_event

    paid = paid_use_event_id is not None
    if not paid and getattr(attack.power, "area", None) is not None:
        from kirby_combat.actions.area_attack import resolve_area_attack_in_session

        return resolve_area_attack_in_session(
            session, attack, template, roller=roller,
            declaration_event_id=declaration_event_id,
            action_type=action_type, combat_type=combat_type,
            payload_extras=payload_extras,
        )
    if not paid and getattr(attack.power, "damage_over_time", None) is not None:
        from kirby_combat.lingering import resolve_damage_over_time_use

        return resolve_damage_over_time_use(
            session, attack, template, roller=roller,
            declaration_event_id=declaration_event_id,
            action_type=action_type, combat_type=combat_type,
            payload_extras=payload_extras,
        )

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
    activated = None if paid else _activation_check(session, attack, roller)
    if activated is not None and not activated["activated"]:
        failed_session, failed = _record_failed_activation(
            session, attack, activated,
            declaration_event_id=declaration_event_id,
            action_type=action_type,
        )
        failed_session = apply_side_effects(
            failed_session, attack, template, roller=roller, failed=True)
        return failed_session, failed

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

    # A STANDING BLOCK MEETS THE BLOW HERE, before the blow is rolled ---
    # 6E2 p.59: "If he succeeds, he Blocks the attack and takes no damage".
    # Asked at the door every hand-to-hand attack reaches, against the
    # attack as it will be rolled (folded and covered just above). See
    # `actions/reactive/blocking.py`.
    from kirby_combat.actions.reactive.blocking import try_block
    from kirby_combat.sense_penalties import HTH, RANGED

    s, block = try_block(
        session, attack, template,
        combat_type=combat_type or (
            RANGED if getattr(attack.power, "is_ranged", False) else HTH),
        roller=roller or session.dice_roller,
    )
    if block is not None and block.success:
        return _record_blocked_attack(
            s, attack, template, block,
            declaration_event_id=declaration_event_id,
            action_type=action_type,
        )
    session = s

    result = resolve_attack(attack, template)

    # ROLLING WITH THE PUNCH (6E2 p.90): "after the opponent's Attack Roll
    # succeeds, but before he rolls damage". A defender who chose it when
    # asked (`loop/reactions.py`) rolls here, and a success halves what he
    # takes "after defenses" --- the same `damage_taken_factor` a Thrown
    # man's Breakfall uses --- so the pure resolver is asked again with
    # the same dice. See `actions/reactive/roll_with_punch.py`.
    rolled_with = None
    if result.hit and attack.damage_taken_factor == 1.0:
        from kirby_combat.actions.reactive.roll_with_punch import try_roll_with_punch

        session, rolled_with = try_roll_with_punch(
            session, attack, template, roller=roller or session.dice_roller)
        if rolled_with is not None and rolled_with["success"]:
            attack = replace(attack, damage_taken_factor=0.5)
            result = resolve_attack(attack, template)
    rolled_with_punch = bool(rolled_with is not None and rolled_with["success"])

    # THE KNOCKBACK ROLL (6E2 p.116), made here and only for a blow that
    # landed with BODY on its dice: only the session knows two of p.117's
    # modifiers (is the target in the air; is there gravity), and a roll
    # nobody needs is a die drawn out of every seeded fight for nothing.
    # A BODY total below the number of dice can never beat the roll, so
    # nothing is rolled for it either. A caller that rolled its own pool
    # kept it, and the pure resolver has already used it.
    from kirby_combat.impact import after_the_blow, knockback_dice_for

    if result.knockback_owed:
        from kirby_combat.resolution.knockback import knockback_body

        kb_count = knockback_dice_for(session, attack, template,
                                      rolled_with_punch=rolled_with_punch)
        kb_roller = roller or session.dice_roller
        # 6E1 p.329: an Autofire burst's Knockback is its largest hit's BODY
        # plus 1 per other hit, rolled once (`AttackInput.knockback_body_bonus`);
        # Double Knockback doubles the total (6E1 p.336).
        kb_body = knockback_body(attack.power, result.damage.body,
                                 attack.knockback_body_bonus)
        if kb_count and kb_body >= kb_count and kb_roller is not None:
            from kirby_combat.resolution.knockback import compute_knockback

            pool = kb_roller.roll_dice(kb_count)
            kb = compute_knockback(
                body=kb_body, knockback_dice=list(pool),
                kb_resistance_m=int(result.defense.knockback_resistance),
                knockback_multiplier=template.knockback_multiplier,
                template=template,
            )
            result = _replace(result, knockback=kb,
                              audit_trail=[*result.audit_trail, *kb.audit])

    attacker_id = attack.attacker.id
    target_id = attack.target.id
    now = datetime.now(timezone.utc)

    # The damage, as its own typed row. See `_apply_damage`: this is the
    # event `apply_event` folds, and it goes in BEFORE the
    # `ActionResolved` that describes the exchange, because the STUN is
    # gone the moment the shot lands.
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
    # Recorded here beside the damage, and through the same door: an END
    # spend is a `VitalsChanged` row and `apply_event` applies it.
    if not paid:
        s = _spend_attack_end(s, attack.attacker, int(result.end_spent or 0),
                              template, power=attack.power)

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
    # WHERE THE BLOW SENT HIM. Knockback moves him and hurts him, and a
    # man hit on a ledge may lose his footing (`impact.after_the_blow`).
    # Here, after his damage and before the row, so the row can say where
    # he went and that he went down (`statuses.FELL`).
    s, landed = after_the_blow(
        s, attack, result, roller=roller or session.dice_roller,
        template=template,
    )
    # A Knockback impact or a fall is damage of its own, checked against
    # CON on its own (6E2 p.105): it can Stun a man the blow did not.
    if (_impact_stunned(landed) and "Stunned" not in status_changes):
        status_changes = [*status_changes, "Stunned"]
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
        # A paid application (an Area's victim, a lingering dose) is not a
        # firing: the use's own row carries the id that spends the Charge.
        "power_source_id": (None if paid
                            else getattr(attack.power, "source_id", None)),
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

    if rolled_with is not None:
        result_payload["rolled_with_punch"] = rolled_with

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

    # THE MANEUVER'S OWN KEYS, before the row is built. See
    # `payload_extras` in the docstring: this is the seam that replaced an
    # edit of an already-committed event.
    if payload_extras is not None:
        extras = payload_extras(result)
        # Two writers of who went down -- a maneuver's Target Falls and the
        # blow's Knockback -- so the lists are joined, not overwritten.
        from kirby_combat.statuses import FELL

        if FELL in landed and FELL in extras:
            extras = {**extras, FELL: sorted(set(extras[FELL]) | set(landed[FELL]))}
        result_payload.update(landed)
        result_payload.update(extras)
    else:
        result_payload.update(landed)

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

    if not paid:
        # 6E1 p.395: an "always occurs" Side Effect lands on every use.
        s = apply_side_effects(s, attack, template, roller=roller, failed=False)
        # A BLOW THAT LANDED HAND TO HAND TOUCHED HIM: a Damage Shield, or a
        # Surface somebody laid on either man, hurts the other one (6E1
        # p.323: "Any attacker who makes a successful HTH Combat attack
        # against a character with a Damage Shield takes the damage", and
        # the shield's wearer's own punch carries it too).
        from kirby_combat.sense_penalties import HTH as _HTH

        hand_to_hand = (combat_type == _HTH if combat_type is not None
                        else not getattr(attack.power, "is_ranged", False))
        if result.hit and hand_to_hand:
            from kirby_combat.standing_areas import contact_doses

            s = contact_doses(s, attacker_id, target_id, template=template,
                              roller=roller or session.dice_roller,
                              contact_event_id=resolved.id)
        # 6E1 p.129: a Constant attack that hit is maintained from here.
        if result.hit and getattr(attack.power, "constant", False):
            from kirby_combat.lingering import begin_lingering

            s = begin_lingering(s, attacker_id=attacker_id,
                                target_id=target_id, power=attack.power)

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
            # The caller's roller, as `_activation_check` uses: one source
            # of randomness for the whole resolution, so a seeded fight
            # stays seeded and a session with no roller of its own works.
            roller=roller or session.dice_roller,
        )

    return s, result


#: 6E1 p.397's own worked example: Arkelos's Major Side Effect on a
#: 40-point Blast is "30 Active Points of damage (Blast 6d6)" --- 5 Active
#: Points to the die.
SIDE_EFFECT_ACTIVE_POINTS_PER_DIE = 5


def apply_side_effects(session: CombatSession, attack: AttackInput, template,
                       *, roller, failed: bool) -> CombatSession:
    """Side Effects on the attacker, when they occur (6E1 p.395-397).

    When: "Each time the character's attempt to activate or use the power
    fails" (``failed``) --- the engine's failing roll is the Activation Roll
    (6E1 p.375) --- or on every use when bought "occurring every time he
    uses the power".

    What: the book leaves the effect to the character's description ("The
    exact nature of a Side Effect is up to the character"), and the build
    carries it only as words. RULING, labelled: the engine applies the
    table's size (Minor 15 AP or 1/4 the power's, Major 30 or 1/2, Extreme
    60 or all, 6E1 p.396) as Normal Damage at 5 Active Points a die --- the
    book's own example, Arkelos's "30 Active Points of damage (Blast 6d6)"
    --- with "no defenses against the Side Effect" and "no Attack Roll"
    (p.397). The build's words ride on the row so a reader sees what the
    character meant.

    The deleted api driver surfaced the modifier as a flag and did nothing.
    """
    spec = getattr(attack.power, "side_effects", None)
    if spec is None or not (failed or spec.always_occurs):
        return session
    victim_id = getattr(attack.attacker, "id", None)
    if victim_id not in session.combatants:
        return session
    from kirby_combat.models import AttackPower, DiceValues
    from kirby_combat.resolution.damage import compute_damage
    from kirby_combat.session.apply import apply_event

    points = spec.severity.active_points(int(attack.power.active_points or 0))
    if spec.environment_only:
        # 6E1 p.396: it affects "the environment around the character
        # instead of the character himself", and "the character should
        # rarely, if ever, be allowed to cause damage to others with it or
        # derive any sort of combat advantage". So it happens, on the same
        # occasions as any Side Effect, and it is written down --- and it
        # moves no number in the fight. Nobody's STUN, no Attack Roll.
        last = next((e for e in reversed(session.event_log)
                     if getattr(e, "kind", "") == "ActionResolved"), None)
        return apply_event(session, ActionResolved(
            id=str(uuid.uuid4()), session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc),
            author=make_author_combatant(victim_id),
            declaration_event_id=getattr(last, "declaration_event_id", "") or "",
            result_payload={
                "kind": "side_effect", "target_id": None,
                "on_environment": True,
                "power_name": getattr(attack.power, "name", None),
                "severity": spec.severity.value, "active_points": points,
                "on_failure": failed, "stun_dealt": 0, "body_dealt": 0,
                "status_changes": [], "text": spec.text,
            },
        ))
    dice = max(1, points // SIDE_EFFECT_ACTIVE_POINTS_PER_DIE)
    blast = AttackPower(
        xmlid="SIDEEFFECTS", name="Side Effect", damage_dice=dice,
        half_die=False, plus_one=False, damage_type="normal",
        defense_type="pd", range_m=0.0, uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
    )
    damage = compute_damage(
        blast, DiceValues(damage=(roller or session.dice_roller).roll_dice(dice)),
        template,
    )
    victim = session.combatants[victim_id]
    stun, body = int(damage.stun), int(damage.body)
    s, _ = record_vitals_change(session, victim_id, stun=-stun, body=-body,
                                reason="side_effect")
    status_changes = determine_status_changes(
        stun_before=victim.current_stun, stun_after=victim.current_stun - stun,
        body_before=victim.current_body, body_after=victim.current_body - body,
        con=adjusted_con(s, victim), max_body=victim.max_body,
    )
    last = next((e for e in reversed(s.event_log)
                 if getattr(e, "kind", "") == "ActionResolved"), None)
    return apply_event(s, ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id,
        sequence=len(s.event_log) + 1, timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(victim_id),
        declaration_event_id=getattr(last, "declaration_event_id", "") or "",
        result_payload={
            "kind": "side_effect", "target_id": victim_id,
            "power_name": getattr(attack.power, "name", None),
            "severity": spec.severity.value, "active_points": points,
            "dice": dice, "on_failure": failed,
            "stun_dealt": stun, "body_dealt": body,
            "status_changes": status_changes, "text": spec.text,
        },
    ))


def resolve_mental_blast_in_session(
    session: CombatSession,
    attacker: StatBlockCombatant,
    target: StatBlockCombatant,
    damage_dice_values: list[int],
    *,
    to_hit: "MentalToHitResult",
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

    # The damage, as its own typed row. See `_apply_damage`: this is the
    # event `apply_event` folds, and it goes in BEFORE the
    # `ActionResolved` that describes the exchange, because the STUN is
    # gone the moment the shot lands.
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

    from kirby_combat.mental.recording import to_hit_payload

    result_payload: dict[str, Any] = {
        "kind": action_type,
        **to_hit_payload(to_hit),
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
    doing so on this default path, THIS function opens an Abort window on
    ``session.timeline.aborts`` (6E2 p.24: it spends one Phase and locks
    him out until that Phase has passed) -- and uses
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

    ``Block.acts_first_priority`` (6E2 p.60, "ACTING FIRST") is asked
    here, and the answer GOES IN THE LOG: a successful Block emits a
    ``BlockPriorityGained``, which ``apply_event`` folds onto
    ``Timeline.block_priority``. It used to be returned to the caller and
    nowhere else, on the reasoning that no driver held a
    ``CombatSession`` and its ``Encounter`` together — and that was the
    one piece of fight state carried by no event at all. A consumer that
    persists the rows and rebuilds the Encounter from the session's own
    timeline between steps held an empty mapping, so the blocker won his
    Block in the live fight and lost his priority in the replayed one.

    The mapping is still RETURNED, unchanged, for a caller that also
    wants to set it on an ``Encounter`` by hand
    (``Encounter.record_block_priority``); the return value is now a
    convenience over a fact the log already carries rather than the only
    copy of it.

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

    # 6E2 p.60, INTO THE RECORD. One event per entry (there is at most
    # one), emitted only on a success -- a failed Block earns nothing and
    # a row saying so would be a row saying nothing.
    for blocker, attacker in priority.items():
        s = apply_event(s, BlockPriorityGained(
            id=str(uuid.uuid4()),
            session_id=s.id,
            sequence=len(s.event_log) + 1,
            timestamp=now,
            author=make_author_combatant(blocker),
            blocker_id=blocker,
            attacker_id=attacker,
        ))

    return s, result, priority


__all__ = [
    "apply_side_effects",
    "resolve_attack_in_session",
    "resolve_mental_blast_in_session",
    "resolve_block_in_session",
    "ACCEPTED_ACTION_KINDS",
    "ActionKind",
]
