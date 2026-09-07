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

WHAT IS NOT IMPLEMENTED, and is named rather than faked: the POOLED
resolution. Joining is a per-Phase act and this engine drives one actor per
Phase, so the window fills across Phases; resolving every participant's
attack at the moment it fills is a scheduling decision the loop does not
make today. ``window_for`` exposes who is in, so a consumer can pool; the
engine does not yet do it for them.
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
    not well. A Characteristic-based Skill Roll is 9 + CHAR/5 (6E1 p.58).
    """
    skills = {
        (getattr(s, "xmlid", "") or "").upper()
        for s in (getattr(actor.hero, "skills", None) or [])
    }
    stats = actor.combat_stats()
    if "TEAMWORK" in skills:
        return "Teamwork", max(8, 9 + int(stats.dex) // 5)
    if "TACTICS" in skills:
        int_score = int(actor.hero.characteristic_value("INT") or 10)
        return "Tactics", 9 + int_score // 5
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
