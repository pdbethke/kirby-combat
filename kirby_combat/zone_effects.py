"""What a place does to whoever is standing in it, Segment by Segment.

`construct_effects.resolve_construct_effect` has decided, for a long time,
whether a hazard zone touches its occupant --- fire against a man with
defenses, water against a man who cannot swim --- and nothing in the engine
called it: it was re-exported and read by the parked api driver, which went
with kirby-api 70ad60f. So nobody in a burning building ever burned and
nobody in the river ever drowned.

This is the caller, at the start of every Segment (`loop/run.py`), for every
construct whose effect is ``every_segment``. A zone's ``on_enter`` /
``on_pass`` effects belong to movement and are not fired here.

FIRE (``damage``): the zone's dice, Normal or Killing as authored, every
Segment, through the same damage pipeline an attack takes --- defenses,
Stun, Knockout --- with no Attack Roll, because a place does not miss.
The deleted driver rolled the dice, subtracted PD or ED and took STUN only.

DROWNING (``suffocation``) is NOT a per-Segment loss, whatever the zone's
trigger says, and this does not port `SUFFOCATION_BODY_PER_SEGMENT`. 6E2
p.132: "A character who holds his breath ... expends a minimum of 1 END per
Phase ... A character who runs out of END while not breathing expends STUN
as END (see 6E2 131). A character who runs out of STUN then loses BODY,
drowning at -1 BODY/Phase ... All characters drown at a minimum SPD of 2."
And 6E2 p.133 prices STUN as END: "1d6 STUN Only damage for every 2 'END'
(or fraction thereof) used, and no defense is allowed". So it fires in the
Segments he has a Phase in, at SPD 2 or better.

NOT BUILT: ``status`` zones (the driver skipped them too: it "never applies
the status, so emitting a note would claim an effect that didn't happen"),
and 6E2 p.132's "does not get to Recover" while holding his breath.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

#: 6E2 p.132: "All characters drown at a minimum SPD of 2".
DROWNING_MINIMUM_SPD = 2
#: 6E2 p.132: "expends a minimum of 1 END per Phase".
HOLDING_BREATH_END_PER_PHASE = 1
#: 6E2 p.133: STUN as END, "1d6 ... for every 2 'END' (or fraction thereof)".
STUN_AS_END_PER_DIE = 2
#: 6E2 p.132: "drowning at -1 BODY/Phase".
DROWNING_BODY_PER_PHASE = 1


def _apply(session, event):
    from kirby_combat.session.apply import apply_event

    return apply_event(session, event)


def _triggered(session, construct_id: str, combatant_id: str, effect: dict):
    from kirby_combat.session.events import EnvironmentalTriggered, make_author_engine

    event = EnvironmentalTriggered(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        hazard_id=construct_id, affected_combatants=[combatant_id],
        effect=effect,
    )
    return _apply(session, event), event.id


def _outcome(session, cause_id: str, combatant_id: str, construct_id: str,
             *, stun: int, body: int, status_changes: list[str], kind: str):
    """The row the status folds read (`statuses.py` folds an
    ``ActionResolved`` naming ``target_id``)."""
    from kirby_combat.session.events import ActionResolved, make_author_engine

    return _apply(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        declaration_event_id=cause_id,
        result_payload={
            "kind": kind, "target_id": combatant_id,
            "construct_id": construct_id, "stun_dealt": stun,
            "body_dealt": body, "status_changes": status_changes,
        },
    ))


def _burn(session, construct, combatant_id: str, *, template, roller):
    from kirby_combat.actions import resolve_attack
    from kirby_combat.adjustments import adjusted_con
    from kirby_combat.models import AttackInput, AttackPower, DiceValues, ToHitResult
    from kirby_combat.resolution.status import determine_status_changes
    from kirby_combat.vitals import record_vitals_change

    eff = construct.effect
    dice = int(eff.damage_dice or 0)
    if dice <= 0:
        return session
    kind = (eff.damage_type or "normal").lower()
    killing = kind == "killing"
    # Fire and energy are Energy attacks against ED; the rest are physical.
    defense = "ed" if kind in ("energy", "fire") else "pd"
    victim = session.combatants[combatant_id]
    power = AttackPower(
        xmlid="HAZARD", name=str(construct.obj_id), damage_dice=dice,
        half_die=False, plus_one=False,
        damage_type="killing" if killing else "normal", defense_type=defense,
        range_m=None, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0,
    )
    fixed = ToHitResult(
        hit=True, roll=0, target_number=0, margin=0, effective_ocv=0,
        effective_dcv=0, range_penalty=0, hit_location_penalty=0, csl_bonus=0,
        audit=[f"{construct.obj_id}: a place does not miss"],
    )
    result = resolve_attack(AttackInput(
        attacker=victim, target=victim, power=power, distance_m=None,
        aim=None, fixed_to_hit=fixed,
        dice=DiceValues(damage=roller.roll_dice(dice),
                        hit_location=roller.roll_dice(3),
                        stun_multiplier=roller.roll_dice(1)),
    ), template)
    session, cause = _triggered(session, construct.obj_id, combatant_id, {
        "kind": "damage", "dice": dice, "damage_type": kind,
        "stun": result.stun_dealt, "body": result.body_dealt,
    })
    if result.stun_dealt or result.body_dealt:
        session, _ = record_vitals_change(
            session, combatant_id, stun=-result.stun_dealt,
            body=-result.body_dealt, reason="hazard")
    status = determine_status_changes(
        stun_before=victim.current_stun,
        stun_after=victim.current_stun - result.stun_dealt,
        body_before=victim.current_body,
        body_after=victim.current_body - result.body_dealt,
        con=adjusted_con(session, victim), max_body=victim.max_body,
    )
    return _outcome(session, cause, combatant_id, construct.obj_id,
                    stun=result.stun_dealt, body=result.body_dealt,
                    status_changes=status, kind="construct_effect")


def _drown(session, construct, combatant_id: str, *, roller):
    """One Phase of not breathing (6E2 p.132-133)."""
    from kirby_combat.adjustments import adjusted_con
    from kirby_combat.resolution.status import determine_status_changes
    from kirby_combat.tables import segments_for_spd
    from kirby_combat.vitals import record_vitals_change

    victim = session.combatants[combatant_id]
    spd = max(DROWNING_MINIMUM_SPD, int(victim.combat_stats().spd))
    if session.timeline.segment not in segments_for_spd(spd):
        return session
    need = HOLDING_BREATH_END_PER_PHASE
    have_end = max(0, int(victim.state.current_end))
    end = min(need, have_end)
    owed = need - end
    stun = body = 0
    if owed:
        if int(victim.state.current_stun) > 0:
            dice = -(-owed // STUN_AS_END_PER_DIE)
            stun = sum(roller.roll_dice(dice))
        else:
            # "If a character is already at 0 STUN or below when he runs
            # out of END, he starts burning BODY right away."
            body = DROWNING_BODY_PER_PHASE
    session, cause = _triggered(session, construct.obj_id, combatant_id, {
        "kind": "suffocation", "end": end, "stun": stun, "body": body,
    })
    session, _ = record_vitals_change(
        session, combatant_id, end=-end, stun=-stun, body=-body,
        reason="holding_breath")
    status = determine_status_changes(
        stun_before=victim.current_stun, stun_after=victim.current_stun - stun,
        body_before=victim.current_body, body_after=victim.current_body - body,
        con=adjusted_con(session, victim), max_body=victim.max_body,
    )
    return _outcome(session, cause, combatant_id, construct.obj_id,
                    stun=stun, body=body, status_changes=status,
                    kind="construct_effect")


def zone_effects_for_segment(session: "CombatSession", *, template, roller):
    """Every ``every_segment`` zone effect, on everyone standing in one."""
    from kirby_combat.construct_effects import resolve_construct_effect
    from kirby_world.construct import constructs_containing

    scene = getattr(session, "scene", None)
    if scene is None:
        return session
    zones = [c for c in (getattr(scene, "constructs", None) or [])
             if getattr(getattr(c, "effect", None), "trigger", None) == "every_segment"]
    if not zones:
        return session
    positions = getattr(scene, "combatant_positions", None) or {}
    for combatant_id in list(session.combatants):
        here = positions.get(combatant_id)
        if here is None:
            continue
        for construct in constructs_containing(here, zones):
            victim = session.combatants[combatant_id]
            res = resolve_construct_effect(construct, victim, segment_tick=True)
            if res is None:
                continue
            if res.outcome == "damage":
                session = _burn(session, construct, combatant_id,
                                template=template, roller=roller)
            elif res.outcome == "suffocating":
                session = _drown(session, construct, combatant_id, roller=roller)
    return session
