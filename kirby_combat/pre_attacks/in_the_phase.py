"""What a Presence Attack does to the PHASE --- the attacker's and the target's.

Three rules the deleted driver (the parked consumer's driver, removed in kirby-api 70ad60f) enforced
and the engine's loop did not:

1. **A Presence Attack takes No Time** (6E2 p.25, Actions Table: "Make a
   Presence Attack --- No Time"; p.20: a character may make one "or perform
   any other Actions that take no time" even on top of a Full Phase Action).
   The loop spent the attacker's Phase on it, so shouting cost as much as
   shooting and nobody ever did both.

   ONE PER PHASE IS A RULING, NOT THE BOOK. p.20 says Actions that take no
   time may be performed "as often as he wishes". A chooser offered a free
   action with no limit can pick it forever --- the driver's first version
   did exactly that and looped without end --- and the dice of a second
   shout in the same breath would be a second roll at the same men for the
   same moment. So: one Presence Attack per Phase, in his own Phase. Recorded
   here as a GM ruling.

2. **Impressed: he hesitates** (6E2 p.139, at PRE: "He hesitates enough so
   that the attacker may act before him that Phase"). `presence_state` has
   folded `yields_to_id` for a long time and nothing read it. Now, at the
   top of his next Phase, if the man who impressed him still has a Phase to
   come in this Segment, he steps back behind him (`PresenceYielded`).

3. **Very impressed: a Half Phase Action only** (6E2 p.139, at PRE+10: he
   "only performs a Half Phase Action during his next Phase").
   `PresenceTier.half_phase` was never read.

"HIS NEXT PHASE" is read off the log: a result is owed until the target
next spends a Phase (`PhaseSpent`). That is the driver's "the flag is
cleared whether or not the defer fires", stated as a fold instead of a
column, so a fight replayed from its rows hesitates exactly where the fight
that ran did.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.session.combat_session import CombatSession

#: The kinds that ARE a Presence Attack.
PRESENCE_KINDS = frozenset({"presence_attack", "presence_attack_group"})

#: What a Half Phase Action excludes: every offer that is a Full Phase, or
#: that is two Half Phases (a Half Move AND an attack). 6E2 p.20: "any
#: Action which requires an Attack Roll" is a Half Phase Action that ends
#: the Phase, so a very impressed man may still attack --- what he may not
#: do is move and attack, or do anything that takes the whole Phase.
HALF_PHASE_EXCLUDED: dict[str, str] = {
    "recover": "taking a Recovery is a Full Phase Action (6E2 p.20)",
    "set": "Set takes a Full Phase (6E2 p.81)",
    "multiple_attack": "the Multiple Attack Maneuver is a Full Phase Action "
                       "(6E2 p.20, p.75)",
    "sweep": "a Sweep is the HTH Multiple Attack, a Full Phase Action "
             "(6E2 p.20, p.75)",
    "rapid_fire": "Rapid Fire is the Ranged Multiple Attack, a Full Phase "
                  "Action (6E2 p.20, p.75)",
    "move": "the offer moves up to his whole movement, a Full Move "
            "(6E2 p.26)",
    "disengage": "a full combat move away, a Full Move (6E2 p.26)",
    "reposition": "moves up to his whole movement, a Full Move (6E2 p.26)",
    "reposition_vantage": "moves up to his whole movement, a Full Move "
                          "(6E2 p.26)",
    "reposition_push": "a Pushed Full Move (6E2 p.26)",
    "move_by": "a Move By attacks \"while doing a Full Move\" (6E2 p.72)",
    # 6E2 p.72 allows a Half-Phase Move Through on a Half Move; this
    # engine's resolver makes the Full-Move one (`actions/move_through.py`,
    # phase_cost "full"), so that is the one excluded.
    "move_through": "a Move Through attacks \"at the end of a Full Move\" "
                    "(6E2 p.72)",
    "move_strike": "a Half Move AND an attack: two Half Phase Actions "
                   "(6E2 p.20)",
    "reposition_strike": "a Half Move AND an attack: two Half Phase Actions "
                         "(6E2 p.20)",
    # RULING: 6E1 p.70 rates climbing per Phase and says nothing of halves,
    # so a climb is read as the Phase's movement.
    "climb": "climbing is rated per Phase (6E1 p.70); ruled a Full Phase",
    "climb_fast": "climbing is rated per Phase (6E1 p.70); ruled a Full "
                  "Phase",
    "change_identity": "an Only In Alternate Identity change takes at least "
                       "a Full Phase (6E1 p.389)",
}


def _since_his_last_phase(session: "CombatSession", combatant_id: str) -> list:
    """The log after the last Phase this combatant spent."""
    log = session.event_log
    for index in range(len(log) - 1, -1, -1):
        evt = log[index]
        if (getattr(evt, "kind", None) == "PhaseSpent"
                and getattr(evt, "combatant_id", None) == combatant_id):
            return log[index + 1:]
    return list(log)


def _in_this_phase(session: "CombatSession", combatant_id: str) -> list:
    """The log since his last Phase AND within this Segment.

    A Phase never spans Segments (6E2 p.18). A man Holding his Action can
    make a No-Time Presence Attack out of turn (`loop/reactions.ask_holders`)
    without spending anything, and reading back only to his last
    `PhaseSpent` would count that attack as made in his NEXT Phase ---
    taking its Presence offer away and treating that Phase as already
    begun. What LANDED on him since his last Phase (`_owed_tiers`) is a
    different question and keeps the wider window.
    """
    log = _since_his_last_phase(session, combatant_id)
    for index in range(len(log) - 1, -1, -1):
        if getattr(log[index], "kind", None) == "SegmentAdvanced":
            return log[index + 1:]
    return log


def presence_attack_made_this_phase(
    session: "CombatSession", combatant_id: str,
) -> bool:
    """Has he already used this Phase's one free Presence Attack?"""
    return any(
        getattr(evt, "kind", None) == "ActionDeclared"
        and getattr(evt, "combatant_id", None) == combatant_id
        and getattr(evt, "action_type", None) in PRESENCE_KINDS
        for evt in _in_this_phase(session, combatant_id)
    )


def phase_already_begun(session: "CombatSession", combatant_id: str) -> bool:
    """Is this the SAME Phase coming back to him?

    True after a free Presence Attack, or after he stepped back behind the
    man who impressed him: in both his slot is still unspent and the loop
    hands it to him again. The rolls owed "at the top of his Phase" ---
    Breakout Rolls, a rage roll --- were made the first time and are not
    owed twice.
    """
    if presence_attack_made_this_phase(session, combatant_id):
        return True
    # A Zero Phase change of identity (Instant Change, 6E1 p.272) leaves
    # the Phase his in the same way; see `kirby_combat/identity.py`.
    if any(getattr(evt, "kind", None) == "IdentityChanged"
           and getattr(evt, "combatant_id", None) == combatant_id
           for evt in _since_his_last_phase(session, combatant_id)):
        return True
    return any(
        getattr(evt, "kind", None) == "PresenceYielded"
        and getattr(evt, "target_id", None) == combatant_id
        for evt in _in_this_phase(session, combatant_id)
    )


def _owed_tiers(session: "CombatSession", combatant_id: str):
    """`(tier rule, attacker id)` for each Presence result landed on him
    since his last Phase and not yet yielded to, oldest first."""
    from kirby_combat.pre_attacks.presence_effects import effect_for_tier
    from kirby_combat.session.effects import presence_state

    if not presence_state(session, combatant_id).is_active:
        return []
    out = []
    for evt in _since_his_last_phase(session, combatant_id):
        if getattr(evt, "target_id", None) != combatant_id:
            continue
        kind = getattr(evt, "kind", None)
        if kind == "PresenceApplied":
            rule = effect_for_tier(getattr(evt, "tier", "") or "")
            if rule is not None:
                out.append((rule, getattr(evt, "attacker_id", "") or ""))
        elif kind == "PresenceYielded":
            out = [(rule, None) for rule, _ in out]
    return out


def hesitation_owed(session: "CombatSession", combatant_id: str) -> str | None:
    """Who he must let act first this Phase, or None (6E2 p.139)."""
    owed = [attacker for rule, attacker in _owed_tiers(session, combatant_id)
            if rule.yields and attacker]
    return owed[-1] if owed else None


def half_phase_only(session: "CombatSession", combatant_id: str) -> bool:
    """Is this Phase limited to a Half Phase Action (6E2 p.139, PRE+10)?"""
    return any(rule.half_phase for rule, _ in _owed_tiers(session, combatant_id))


def limit_to_half_phase(menu: Iterable["LegalAction"]) -> list["LegalAction"]:
    """The offers a very impressed man may still take."""
    return [a for a in menu if a.kind not in HALF_PHASE_EXCLUDED]


def can_yield_to(session: "CombatSession", target_id: str, attacker_id: str) -> bool:
    """Does the attacker still have a Phase AFTER the target's in this Segment?

    Hesitating to let somebody go first is pointless once he has gone, or
    when he has no Phase this Segment at all.
    """
    from kirby_combat.enumeration import is_down

    attacker = session.combatants.get(attacker_id)
    if attacker is None or is_down(attacker):
        return False
    seen_target = False
    for slot in session.timeline.acting_order:
        if slot.has_acted:
            continue
        if slot.combatant_id == target_id and not seen_target:
            seen_target = True
            continue
        if seen_target and slot.combatant_id == attacker_id:
            return True
    return False


def yield_phase(
    session: "CombatSession", target_id: str, attacker_id: str,
) -> "CombatSession":
    """Record the hesitation; `apply_event` moves his slot behind the attacker's."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import PresenceYielded, make_author_engine

    return apply_event(session, PresenceYielded(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        target_id=target_id, attacker_id=attacker_id,
        turn=int(session.timeline.turn), segment=int(session.timeline.segment),
    ))
