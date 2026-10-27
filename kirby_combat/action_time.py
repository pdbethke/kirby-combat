"""How long an Action takes, and what is left of the Phase after it.

6E2 p.20 sorts every Action a character can perform in a Phase into four
kinds, and the Actions Table (6E2 p.25) prices the common ones:

* **Full Phase Actions** take the whole Phase: a Full Move, a Recovery, the
  Multiple Attack, Set, recovering from being Stunned.
* **Half Phase Actions** take half of it: "a character can perform two Half
  Phase Actions per Phase" --- a Half Move, getting to one's feet, drawing a
  weapon, picking up a Disarmed one, most PER and Skill Rolls.
* **Attack Actions** "only take a Half Phase, but must be the last action the
  character performs in the Phase ... a character can Half Move and then
  attack, but can't attack and then Half Move". Dodging and Blocking are
  Attack Actions too.
* **Zero Phase Actions** (activating a power, shifting a Multipower, using
  STR Casually) may be performed "at the beginning of a Phase or after
  performing a Half Phase Action, but not after performing an Attack Action
  or a Full Phase Action"; and **Actions which take no time** (a Presence
  Attack) whenever he wishes.

THE LOOP GAVE A MAN ONE ACTION A PHASE. Every offer spent the slot, except
four hand-written Zero Phase exits in `loop/run.py` (Instant Change, a
Multipower reallocation, raising a Damage Shield, a Presence Attack), each
with its own branch and its own way of telling the next `run_phase` that the
Phase had already begun. Standing up took the Phase; so did picking a weapon
up. This module is the one table and the one fold all of them read.

HOW A PHASE CONTINUES. The loop never resolves two choices in one call: a
networked consumer steps one declaration at a time. After an Action that does
not end the Phase, `run_phase` writes `PhaseTimeUsed` and does not spend the
slot, so the next `run_phase` hands the same man the same Phase, with the
menu cut to what is still legal (`rest_of_phase`). The same mechanism the
Zero Phase exits already used, now with a record of how much was used.

RULINGS (6E2 p.25: "The GM must decide how long an Action not listed on the
Action Table takes, using the listed examples as guidelines"), each named on
its row of `KIND_TIMES` below.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.session.combat_session import CombatSession


class ActionTime(str, enum.Enum):
    """The time an Action takes (6E2 p.20)."""

    #: "Actions which take no time ... whenever he wishes" (a Presence Attack).
    NO_TIME = "no_time"
    #: A Zero Phase Action: at the start of the Phase or after a Half Phase
    #: Action, never after an Attack Action or a Full Phase Action.
    ZERO = "zero"
    #: Half of the Phase; he may take another Half Phase Action after it.
    HALF = "half"
    #: An Attack Action: a Half Phase that ENDS the Phase.
    ATTACK = "attack"
    #: The whole Phase.
    FULL = "full"
    #: Holding: the rest of his Phase, kept for later (6E2 p.22). Allowed
    #: after a Half Phase Action ("A character may perform a Half Phase
    #: Action and then Hold a Half Phase"), and it ends what he does now.
    HOLD = "hold"
    #: Breaking out of an Entangle or a Grab with full force: the time it
    #: takes is decided by how well it went (6E2 p.126), see `breakout_time`.
    BREAKOUT = "breakout"

    @property
    def ends_the_phase(self) -> bool:
        return self in (ActionTime.ATTACK, ActionTime.FULL, ActionTime.HOLD)


_T = ActionTime

#: Every kind the engine offers, with what it takes and why. Exhaustive on
#: purpose: `test_every_kind_has_a_time` holds it to the resolver registry,
#: and `time_of` raises on a kind that is not here --- a new kind whose time
#: nobody decided is a missing decision, not a Full Phase by default.
KIND_TIMES: dict[str, tuple[ActionTime, str]] = {
    # ── Actions which take no time ─────────────────────────────────────
    "presence_attack": (_T.NO_TIME, "Make a Presence Attack: No Time (6E2 p.25)"),
    "presence_attack_group": (_T.NO_TIME, "Make a Presence Attack: No Time (6E2 p.25)"),
    # ── Zero Phase ─────────────────────────────────────────────────────
    "change_identity_instant": (_T.ZERO, "Instant Change (6E1 p.272)"),
    "reallocate": (_T.ZERO, "Shift a Multipower: 0 Phase (6E2 p.25; 6E1 p.410)"),
    "raise_damage_shield": (_T.ZERO, "\"only ... a Zero Phase Action to activate it\" (6E1 p.323)"),
    # escape_str's Casual offers are ZERO and its full ones BREAKOUT; see
    # `time_of`. The entry here is the full attempt.
    "escape_str": (_T.BREAKOUT, "6E2 p.126; Casual STR is 0 Phase (6E2 p.25)"),
    # ── Half Phase ─────────────────────────────────────────────────────
    "half_move": (_T.HALF, "Use up to half of your meters of movement: 1/2 Phase (6E2 p.25-26)"),
    "move_to_cover": (_T.HALF, "the resolver moves a Half Move (6E2 p.26)"),
    "stand_up": (_T.HALF, "Get to one's feet: 1/2 Phase (6E2 p.25, p.51)"),
    "pick_up_weapon": (_T.HALF, "Pick up Disarmed weapon: 1/2 Phase (6E2 p.25)"),
    # RULING: lifting a loose object to throw is read as picking up a
    # Disarmed weapon; 6E2 p.175 has a light object used "as part of a
    # single Attack Action", and this offer is for the heavy ones.
    "pickup": (_T.HALF, "RULING: as Pick up Disarmed weapon, 1/2 Phase (6E2 p.25)"),
    # 6E2 p.20: "making most PER Rolls or Skill Rolls" is a Half Phase.
    "hide": (_T.HALF, "a Stealth Skill Roll: \"most ... Skill Rolls\" are 1/2 Phase (6E2 p.20)"),
    "charm": (_T.HALF, "an interaction Skill Roll: 1/2 Phase (6E2 p.20)"),
    "persuasion": (_T.HALF, "an interaction Skill Roll: 1/2 Phase (6E2 p.20)"),
    "conversation": (_T.HALF, "an interaction Skill Roll: 1/2 Phase (6E2 p.20)"),
    "trading": (_T.HALF, "an interaction Skill Roll: 1/2 Phase (6E2 p.20)"),
    # RULING: a Teleport out of an Entangle is a Half Move of Teleportation
    # (6E1 p.218 makes it an escape; 6E2 p.26 prices the move).
    "escape_teleport": (_T.HALF, "RULING: a Half Move of Teleportation (6E1 p.218, 6E2 p.26)"),
    # RULING: 6E1 p.424 names the attempt and prices nothing; calling out to
    # a raging friend is read as speaking, held to a Half Phase.
    "snap_out_of_rage": (_T.HALF, "RULING: an attempt to snap him out of it (6E1 p.424), 1/2 Phase"),
    # ── Attack Actions ─────────────────────────────────────────────────
    **{kind: (_T.ATTACK, "Any action that requires an Attack Roll: 1/2 Phase, ends the Phase (6E2 p.20, p.25)")
       for kind in (
           "attack", "strike", "mental_blast", "mind_control", "mind_scan",
           "mental_illusion", "telepathy", "image_decoy", "flash", "entangle",
           "mental_entangle", "aid", "drain", "heal", "dispel", "throw",
           "throw_object", "maneuver", "trip", "disarm", "push", "spread",
           "coordinate", "attack_construct", "darkness_zone", "autofire",
           "autofire_spray", "attack_entangle",
       )},
    "dodge": (_T.ATTACK, "Dodging is an Attack Action (6E2 p.20)"),
    "block": (_T.ATTACK, "Blocking is an Attack Action (6E2 p.20)"),
    "grab": (_T.ATTACK, "Grab: 1/2 Phase, an Attack Action (6E2 p.25)"),
    "haymaker": (_T.ATTACK, "Haymaker: 1/2 Phase, an Attack Action (6E2 p.25)"),
    # RULING: a Barrier is placed, not rolled for; it is read as the power
    # this Phase is for, and so ends it.
    "force_wall": (_T.ATTACK, "RULING: raising a Barrier ends the Phase like an attack"),
    # The victim attacks the Entangle; its result decides the time.
    "escape_attack": (_T.BREAKOUT, "6E2 p.126: what is left of the Phase is decided by the BODY done"),
    "escape_ego": (_T.BREAKOUT, "6E2 p.126, with EGO for STR (6E1 p.219)"),
    # ── Full Phase ─────────────────────────────────────────────────────
    "recover": (_T.FULL, "Take a Recovery: 1 Phase (6E2 p.25)"),
    "set": (_T.FULL, "Set: 1 Phase (6E2 p.25)"),
    "multiple_attack": (_T.FULL, "Multiple Attack: 1 Phase (6E2 p.25)"),
    "sweep": (_T.FULL, "the HTH Multiple Attack: 1 Phase (6E2 p.25, p.75)"),
    "rapid_fire": (_T.FULL, "the Ranged Multiple Attack: 1 Phase (6E2 p.25, p.75)"),
    "move": (_T.FULL, "up to his whole movement: a Full Move (6E2 p.26)"),
    "disengage": (_T.FULL, "a Full Move away (6E2 p.26)"),
    "reposition": (_T.FULL, "up to his whole movement: a Full Move (6E2 p.26)"),
    "reposition_vantage": (_T.FULL, "up to his whole movement: a Full Move (6E2 p.26)"),
    "reposition_push": (_T.FULL, "a Pushed Full Move (6E2 p.26)"),
    "move_by": (_T.FULL, "a Move By at the end of a Full Move (6E2 p.25 note)"),
    "move_through": (_T.FULL, "a Move Through at the end of a Full Move (6E2 p.25 note)"),
    # Two Half Phase Actions offered as one: a Half Move and an attack.
    "move_strike": (_T.FULL, "a Half Move AND an Attack Action, the whole Phase (6E2 p.20)"),
    "reposition_strike": (_T.FULL, "a Half Move AND an Attack Action, the whole Phase (6E2 p.20)"),
    "climb": (_T.FULL, "RULING: climbing is rated per Phase (6E1 p.70)"),
    "climb_fast": (_T.FULL, "RULING: climbing is rated per Phase (6E1 p.70)"),
    "change_identity": (_T.FULL, "\"at least a Full Phase\" (6E1 p.389)"),
    "stabilize": (_T.FULL, "\"Stopping a character from bleeding requires just one Full Phase\" (6E1 p.86)"),
    "reconfigure_vpp": (_T.FULL, "\"Changing powers with the VPP Skill takes a Full Phase\" (6E1 p.413)"),
    # Releasing a Hold on his own Phase is the Phase he had held for.
    "release_held": (_T.FULL, "the Held Action is the Phase it was held from (6E2 p.22)"),
    "hold": (_T.HOLD, "Holding an Action (6E2 p.22)"),
}

#: The offers whose id marks a Casual STR attempt (Grab or Entangle).
_CASUAL_SUFFIXES = ("casual",)


def is_casual(action: "LegalAction") -> bool:
    """A Casual STR escape: "Use STR or a power Casually: 0 Phase" (6E2 p.25)."""
    return action.kind == "escape_str" and action.action_id.endswith(_CASUAL_SUFFIXES)


def time_of(action: "LegalAction") -> ActionTime:
    """What ``action`` takes. Raises on a kind nobody priced."""
    if is_casual(action):
        return ActionTime.ZERO
    try:
        return KIND_TIMES[action.kind][0]
    except KeyError:
        raise ValueError(
            f"no Action time is decided for kind {action.kind!r} "
            f"({action.action_id!r}); add it to action_time.KIND_TIMES with "
            f"its page (6E2 p.20, p.25)"
        ) from None


def breakout_time(resolved) -> ActionTime:
    """What a full-force break-out took, by 6E2 p.126.

    * Entangle: twice its remaining BODY or more frees him "and has a Full
      Phase in which to act (i.e., it takes no time at all)"; at least its
      remaining BODY frees him and he "may perform a Half Phase Action"; less
      and he "may take no more Actions that Phase".
    * Grab: twice the Grabber's BODY frees him with a Full Phase; more than
      the Grabber's frees him but "may take no more Actions that Phase"; and
      failing leaves him held, his Phase gone.

    Read off what the resolver wrote, never re-rolled.
    """
    from kirby_combat.actions.entangle import EntangleResult
    from kirby_combat.actions.grab import GRAB_ESCAPE_REGAINED

    result = resolved.result
    if isinstance(result, EntangleResult):
        regained = result.action_regained
    else:
        outcomes = [
            (e.result_payload or {}).get("outcome")
            for e in resolved.events
            if getattr(e, "kind", None) == "ActionResolved"
            and (e.result_payload or {}).get("type") == "grab_escape"
        ]
        if not outcomes or outcomes[-1] not in GRAB_ESCAPE_REGAINED:
            raise ValueError(
                f"{resolved.action_id!r} recorded no break-out outcome to time "
                f"(6E2 p.126)"
            )
        regained = GRAB_ESCAPE_REGAINED[outcomes[-1]]
    return {"full": ActionTime.ZERO, "half": ActionTime.HALF,
            "none": ActionTime.FULL}[regained]


# ---------------------------------------------------------------------------
# What is left of the Phase: folded from the log
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PhaseSoFar:
    """What he has already done in this Phase."""

    halves_used: int
    #: The kinds of the Half Phase Actions he took, in order.
    half_kinds: tuple[str, ...]
    #: Casual STR used in this Segment (6E1 p.134: "only ... once per
    #: Segment").
    casual_used: bool
    #: Any Action at all that left the Phase his.
    begun: bool


def _time_rows(session: "CombatSession", combatant_id: str):
    from kirby_combat.pre_attacks.in_the_phase import _in_this_phase

    return [e for e in _in_this_phase(session, combatant_id)
            if getattr(e, "kind", None) == "PhaseTimeUsed"
            and e.combatant_id == combatant_id]


def phase_so_far(session: "CombatSession", combatant_id: str) -> PhaseSoFar:
    rows = _time_rows(session, combatant_id)
    halves = [r for r in rows if r.time == ActionTime.HALF.value]
    segment = (session.timeline.turn, session.timeline.segment)
    casual = any(r.action_kind == "escape_str" and r.action_id.endswith(_CASUAL_SUFFIXES)
                 and (r.turn, r.segment) == segment for r in rows)
    return PhaseSoFar(
        halves_used=len(halves),
        half_kinds=tuple(r.action_kind for r in halves),
        casual_used=casual, begun=bool(rows),
    )


def halves_allowed(session: "CombatSession", combatant_id: str) -> int:
    """Two Half Phase Actions in a Phase (6E2 p.20); one for a man very
    impressed by a Presence Attack, who "only performs a Half Phase Action
    during his next Phase" (6E2 p.139)."""
    from kirby_combat.pre_attacks.in_the_phase import half_phase_only

    return 1 if half_phase_only(session, combatant_id) else 2


def halves_left(session: "CombatSession", combatant_id: str) -> int:
    return max(0, halves_allowed(session, combatant_id)
               - phase_so_far(session, combatant_id).halves_used)


def fits_in_a_half(action: "LegalAction") -> bool:
    """May this be taken in a single remaining Half Phase?

    A Half Phase Action, an Attack Action (it ends the Phase), a Zero Phase
    Action (allowed "after performing a Half Phase Action", 6E2 p.20), a
    No-Time Action, a Hold of what is left, or a break-out (whose time p.126
    decides afterwards). Not a Full Phase Action, and not two Half Phase
    Actions offered as one.
    """
    return time_of(action) is not ActionTime.FULL


def rest_of_phase(session: "CombatSession", combatant_id: str,
                  menu: Iterable["LegalAction"]) -> list["LegalAction"]:
    """The menu cut to what may still be done in this Phase.

    With one Half Phase left --- after a first Half Phase Action, or all
    along for a very impressed man --- only what fits in it. Casual STR once
    a Segment (6E1 p.134).
    """
    so_far = phase_so_far(session, combatant_id)
    out = list(menu)
    if so_far.casual_used:
        out = [a for a in out if not is_casual(a)]
    if halves_left(session, combatant_id) <= 1:
        out = [a for a in out if fits_in_a_half(a)]
    return out


def holds_only_a_half(session: "CombatSession", combatant_id: str) -> bool:
    """Is the Action he is Holding the second half of a Phase?

    6E2 p.22: "A character may perform a Half Phase Action and then Hold a
    Half Phase ... and may perform the Held Half Phase Action later." Read off
    the Phase his live Hold was declared in.
    """
    from kirby_combat.loop.reactions import usable_hold

    held = usable_hold(session, combatant_id)
    if held is None:
        return False
    log = session.event_log
    at = next((i for i, e in enumerate(log) if getattr(e, "id", None) == held.id), None)
    if at is None:
        return False
    for evt in reversed(log[:at]):
        kind = getattr(evt, "kind", None)
        if kind == "PhaseSpent" and evt.combatant_id == combatant_id:
            return False
        if (kind == "PhaseTimeUsed" and evt.combatant_id == combatant_id
                and evt.time == ActionTime.HALF.value):
            return True
    return False


def record_time(session: "CombatSession", combatant_id: str,
                action: "LegalAction", time: ActionTime) -> "CombatSession":
    """Write down part of a Phase used by an Action that did not end it."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import PhaseTimeUsed, make_author_engine

    if time.ends_the_phase or time is ActionTime.BREAKOUT:
        raise ValueError(
            f"{action.kind!r} took {time.value}; only an Action that leaves the "
            f"Phase his is recorded as PhaseTimeUsed (the rest spend the slot)"
        )
    return apply_event(session, PhaseTimeUsed(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id=combatant_id, action_kind=action.kind,
        action_id=action.action_id, time=time.value,
        turn=int(session.timeline.turn), segment=int(session.timeline.segment),
    ))


#: The kinds that take the whole Phase, and so never fit in a Half Phase.
FULL_PHASE_KINDS = frozenset(
    kind for kind, (time, _why) in KIND_TIMES.items() if time is ActionTime.FULL)
