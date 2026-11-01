"""Coordinated Attacks — joining a same-Phase strike (6E2 p.46).

Two or more characters can time their attacks to land together. Each makes
a Teamwork roll to join; once the window holds two or more, their attacks
resolve as one coordinated strike and their STUN is POOLED against the
target's CON for the Stunning check --- which is the whole point, since two
attacks that each fall short of CON can together exceed it.

WHERE THE WINDOW LIVES. In the log, like every other timed thing in this
engine. A combatant who joins emits an ``ActionResolved`` naming the target
and the Segment; ``window_for`` folds those forward. Nothing is held in a
dict on the session, which is the same reasoning ``session/effects.py``
gives for Adjustment, Entangle and Flash: a forward fold over the log
cannot desync from the log.

THE ROLL, AND ITS LADDER. 6E2 p.46 makes Teamwork the skill for this. The
parked driver's ladder --- Teamwork, else Tactics, else a flat DEX 8- ---
is carried over unchanged, but its skill lookup was three database queries;
here it reads ``hero.skills`` directly, the same way enumeration reads
interaction skills.

THE POOL IS THE POINT, and ``pooled_stun`` is where it happens. Rather than
rescheduling attacks so they resolve simultaneously --- which a one-actor-
per-Phase loop cannot do --- the pooling is a DERIVATION: sum the STUN that
window members dealt this Segment and compare THAT to CON.

The result is the same and the mechanism is simpler. It also matches how
every other condition in this engine works: `statuses.py` folds Stunned out
of the log rather than storing it, so a Stun that only exists once two
blows are added together is answered the same way as any other.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


@dataclass(frozen=True)
class CoordinationRoll:
    """One attempt to join a coordinated strike."""

    combatant_id: str
    target_id: str
    skill: str
    target_number: int
    roll: int

    @property
    def joined(self) -> bool:
        """3d6 rolled at or under the target number, the standard HERO
        Skill Roll (6E1 p.58)."""
        return self.roll <= self.target_number


def roll_profile(actor) -> tuple[str, int]:
    """The skill this actor coordinates with, and its target number.

    Teamwork first (6E2 p.46 names it), then Tactics, then a flat DEX 8-
    for a character with neither --- anyone can try to time a blow, just
    not well.

    The roll is the SHEET's (`skill_roll_value`, the cost engine's
    computed roll, the door perception and Paramedics use), not 9 + CHAR/5
    worked out here: a Familiarity is "an 8- roll" (6E1 p.62) and bought
    levels add +1 for 2 points (6E1 p.63), and the hand-rolled formula saw
    neither. Like every skill roll in this engine it is the roll as built;
    a Drained DEX does not lower it.

    A flat stat block owns no skills (no `skill_roll_value`, as
    the Trip resolver finds), so it tries on DEX 8-.
    """
    if not hasattr(actor, "skill_roll_value"):
        return "DEX", 8
    for xmlid, skill in (("TEAMWORK", "Teamwork"), ("TACTICS", "Tactics")):
        roll = actor.skill_roll_value(xmlid)
        if roll is not None:
            return skill, int(roll)
    return "DEX", 8


def window_for(
    session: "CombatSession", target_id: str, segment: int,
) -> tuple[str, ...]:
    """Who has joined the coordinated strike on ``target_id`` this Segment.

    Folded forward out of the log. A join is scoped to its Segment, because
    6E2 p.46's whole premise is that the blows land TOGETHER --- a join from
    an earlier Segment is not part of this strike.
    """
    joined: list[str] = []
    for evt in session.event_log:
        if getattr(evt, "kind", None) != "ActionResolved":
            continue
        payload = getattr(evt, "result_payload", None) or {}
        if (
            payload.get("kind") == "coordinate"
            and payload.get("target_id") == target_id
            and payload.get("segment") == segment
            and payload.get("joined")
        ):
            combatant_id = payload.get("combatant_id")
            if combatant_id and combatant_id not in joined:
                joined.append(combatant_id)
    return tuple(joined)


def is_coordinated(
    session: "CombatSession", target_id: str, segment: int,
) -> bool:
    """True once the window holds two or more --- one character cannot
    coordinate with themselves."""
    return len(window_for(session, target_id, segment)) >= 2


def pooled_stun(
    session: "CombatSession", target_id: str, segment: int,
) -> int:
    """Total STUN the coordinated window dealt ``target_id`` this Segment.

    Only attacks by combatants who actually JOINED the window count ---
    joining is what makes the blows simultaneous, and an ally who swung
    independently in the same Segment did not coordinate.

    Zero when the window is not full: one character cannot coordinate with
    themselves, so there is nothing to pool.
    """
    members = window_for(session, target_id, segment)
    if len(members) < 2:
        return 0

    total = 0
    for evt in session.event_log:
        if getattr(evt, "kind", None) != "ActionResolved":
            continue
        payload = getattr(evt, "result_payload", None) or {}
        if payload.get("target_id") != target_id:
            continue
        if payload.get("kind") == "coordinate":
            continue
        # SCOPED TO THE SEGMENT, like the window itself. Blows in different
        # Segments did not land together, whatever the window said -- and
        # summing across Segments would let a fight accumulate a Stun out of
        # attacks minutes apart.
        if int(payload.get("segment", -1)) != segment:
            continue
        author = getattr(getattr(evt, "author", None), "id", None)
        if author in members:
            total += int(payload.get("stun_dealt", 0) or 0)
    return total


def pools_into_a_stun(
    session: "CombatSession", target_id: str, segment: int, con: int,
) -> bool:
    """Whether the coordinated window Stuns the target (6E2 p.106).

    "If the STUN done to a character by a single attack (after subtracting
    defenses) exceeds his CON, he's Stunned." A coordinated strike is one
    attack for this purpose --- which is the whole reason to coordinate, and
    why two blows that each fall short can together put someone down.

    Strictly greater than CON, matching `determine_status_changes`: the book
    says "exceeds", not "meets or exceeds".
    """
    return pooled_stun(session, target_id, segment) > con


def joined_this_segment(session: "CombatSession", combatant_id: str) -> bool:
    """Whether he has already joined a coordinated strike this Segment.
    One strike, one join: the attack he joined with is what is left."""
    segment = session.timeline.segment
    for evt in session.event_log:
        payload = getattr(evt, "result_payload", None) or {}
        if (getattr(evt, "kind", None) == "ActionResolved"
                and payload.get("kind") == "coordinate"
                and payload.get("combatant_id") == combatant_id
                and payload.get("segment") == segment):
            return True
    return False


#: 6E1 p.76: Defense Maneuver II "Eliminates Multiple Attacker Bonuses as to
#: attackers the character can perceive", III "to all attackers, even those
#: which the character cannot perceive". HD's option ids for I-II .. I-IV.
_SPARES_PERCEIVED = frozenset({"TWO"})
_SPARES_ALL = frozenset({"THREE", "FOUR"})


def _defense_maneuver_spares(session: "CombatSession", target, attacker) -> bool:
    from kirby_combat.resolution.surprise import DEFENSE_MANEUVER

    hero = getattr(target, "hero", None) or target
    levels = {
        (getattr(item, "option_id", None) or "").upper()
        for collection in ("skills", "talents", "powers")
        for item in getattr(hero, collection, None) or []
        if (getattr(item, "xmlid", None) or "").upper() == DEFENSE_MANEUVER
    }
    if levels & _SPARES_ALL:
        return True
    if levels & _SPARES_PERCEIVED:
        from kirby_combat.sense_penalties import cannot_perceive

        return attacker is not None and not cannot_perceive(session, target, attacker)
    return False


def multiple_attacker_dcv_delta(
    session: "CombatSession", attacker_id: str, target_id: str, *, dcv: int,
) -> int:
    """The Multiple Attacker Bonus on this attack, as a DCV delta (<= 0).

    6E2 p.51, an OPTIONAL rule (`CombatTemplate.use_multiple_attacker_bonus`):
    "If the attackers successfully Coordinate, the defender suffers a -1 DCV
    for every attacker after the first, down to a minimum of 1/2 DCV ... The
    DCV penalty applies only against those opponents who Coordinate their
    attacks". ``dcv`` is his DCV against this attack before the bonus; the
    floor is half of it, rounded in his favour (6E1 p.14, `apply_cv_factor`).

    RULING, stated: the book's coordinated blows land together and this
    loop's land one after another, so the bonus counts the men who have
    JOINED SO FAR this Segment. The first to swing gains nothing from those
    who join after him.

    Not built: a defender who "ignore[s] some of them to concentrate on a
    more dangerous opponent", and the MCV bonus for Coordinated Mental
    Powers (mental attacks take their own to-hit door).
    """
    if not session.template.use_multiple_attacker_bonus:
        return 0
    members = window_for(session, target_id, session.timeline.segment)
    if attacker_id not in members or len(members) < 2:
        return 0
    target = session.combatants.get(target_id)
    attacker = session.combatants.get(attacker_id)
    if target is None or _defense_maneuver_spares(session, target, attacker):
        return 0
    from kirby_combat.cv_modifiers import apply_cv_factor

    floor = apply_cv_factor(int(dcv), 0.5)
    return -min(len(members) - 1, max(0, int(dcv) - floor))
