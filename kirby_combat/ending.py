"""The end of a fight: its terms, and the one event that ends it.

Two-databases spec §6a; plan ``kirby/docs/superpowers/plans/2026-11-24-fight-end.md``.

ONE WAY OUT. A fight ends only when ``SessionEnded`` is in its log: typed
(`Ending`), naming the winning side's id (or none), and authored by whoever
confirmed it --- the engine for an auto-stop, the GM otherwise. Replay shows
it; a campaign carries a fight's consequences back on it and on nothing else.
Before this module ``SessionEnded`` existed and nothing emitted it, so no
fight's log recorded its end and every consumer re-asked the roster.

THE TERMS ARE IN THE LOG, NOT IN EACH CALL. ``FightTermsStated`` is stated
once as the fight starts, exactly like ``RulingsStated``
(`kirby_combat.rulings.state_rulings`), and ``run_phase`` reads it from the
session. A per-call ``until=`` was a second statement of the fight's rules
that a networked consumer, stepping one Phase per request, could change
between calls, and that a replay could never know. A fight with no terms
refuses to step: there is no default (Peter's no-defaults rule).

HOW THE END IS CONFIRMED IS ITS OWN CHOICE (Peter, 2026-11-24: "we can ask
the gm if thats the end", "or auto-stop", "allow a choice"). ``AUTO_STOP``:
the stop condition is final. ``ASK``: when it holds, the engine proposes the
end (``EndProposed``) and holds the fight still until the GM answers
(`answer_end`); a "no" (``EndDeclined``) carries on, and the same verdict is
not asked again. The GM can end any fight at any time (`call_fight`).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from kirby_combat.roster import LastSideStanding, Roster, StopCondition, Verdict
from kirby_combat.side import Side

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.session.events import EndProposed, SessionEnded


class StopKind(str, Enum):
    """Which condition decides the fight. Named, so the log can carry it."""

    #: Over when at most one side still has someone up (6E1 p.421 for "up").
    LAST_SIDE_STANDING = "last_side_standing"
    #: Over the moment anyone has lost STUN. A scenario condition the GM
    #: chooses, not a book rule.
    FIRST_BLOOD = "first_blood"
    #: Nothing decides it: only the GM ends it (a scripted scene).
    GM_ONLY = "gm_only"


class EndMode(str, Enum):
    """Who confirms the end once the stop condition holds."""

    ASK = "ask"
    AUTO_STOP = "auto_stop"


class Ending(str, Enum):
    """How a fight ended."""

    DECIDED = "decided"
    CALLED = "called"
    STALEMATE = "stalemate"
    TURN_LIMIT = "turn_limit"


@dataclass(frozen=True)
class FightTerms:
    """The fight's stop condition and how its end is confirmed. Both required."""

    stop: StopKind
    end_mode: EndMode


class FightTermsMissing(Exception):
    """The fight was never given its terms, so nothing can say when it ends."""


class FirstBlood:
    """Over once anyone has lost STUN.

    The winner is the one side nobody on which is hurt, when there is
    exactly one; otherwise the fight is over with no winner. (The example
    this was promoted from, ``examples/the_battle_of_four_armies.py``,
    named the HURT man's side as the winner.)
    """

    def decide(self, roster: Roster) -> Verdict:
        hurt = {Side.of(c) for c in roster.combatants
                if c.state.current_stun < c.combat_stats().max_stun}
        if not hurt:
            return Verdict(over=False)
        unhurt = roster.sides - hurt
        return Verdict(over=True,
                       winner=next(iter(unhurt)) if len(unhurt) == 1 else None)


class GmOnly:
    """Never over on its own."""

    def decide(self, roster: Roster) -> Verdict:
        return Verdict(over=False)


_CONDITIONS: dict[StopKind, StopCondition] = {
    StopKind.LAST_SIDE_STANDING: LastSideStanding(),
    StopKind.FIRST_BLOOD: FirstBlood(),
    StopKind.GM_ONLY: GmOnly(),
}


def condition_for(stop: StopKind) -> StopCondition:
    return _CONDITIONS[StopKind(stop)]


# ---- reading the log -----------------------------------------------------

def terms_of(session: "CombatSession") -> FightTerms:
    """The fight's terms, from its log. Raises `FightTermsMissing` if none."""
    for event in session.event_log:
        if getattr(event, "kind", None) == "FightTermsStated":
            return FightTerms(stop=StopKind(event.stop),
                              end_mode=EndMode(event.end_mode))
    raise FightTermsMissing(
        f"session {session.id!r} has no FightTermsStated: state its terms "
        "(kirby_combat.ending.state_terms) as the fight starts")


def ended(session: "CombatSession") -> "SessionEnded | None":
    """The event that ended the fight, or None while it goes on."""
    for event in reversed(session.event_log):
        if getattr(event, "kind", None) == "SessionEnded":
            return event
    return None


def open_proposal(session: "CombatSession") -> "EndProposed | None":
    """The proposal awaiting the GM's answer, if any."""
    for event in reversed(session.event_log):
        kind = getattr(event, "kind", None)
        if kind in ("EndDeclined", "SessionEnded"):
            return None
        if kind == "EndProposed":
            return event
    return None


def declined_verdicts(session: "CombatSession") -> set[tuple[str, str | None]]:
    """(ending, winner) pairs the GM has said no to. Not asked again."""
    return {(e.ending, e.winner) for e in session.event_log
            if getattr(e, "kind", None) == "EndDeclined"}


# ---- writing the log -----------------------------------------------------

def _append(session: "CombatSession", event_cls, *, author, **fields):
    from kirby_combat.session.apply import apply_event
    return apply_event(session, event_cls(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(UTC), author=author, **fields,
    ))


def state_terms(session: "CombatSession", terms: FightTerms) -> "CombatSession":
    """Put the fight's terms on the log. Once, before the fight moves."""
    from kirby_combat.session.events import FightTermsStated, make_author_engine
    return _append(session, FightTermsStated, author=make_author_engine(),
                   stop=StopKind(terms.stop).value,
                   end_mode=EndMode(terms.end_mode).value)


def end_fight(session: "CombatSession", ending: Ending, winner: str | None,
              *, author) -> "CombatSession":
    """Append ``SessionEnded``. Refused if the fight has already ended."""
    from kirby_combat.session.events import SessionEnded
    return _append(session, SessionEnded, author=author,
                   ending=Ending(ending).value, winner=winner)


def propose_end(session: "CombatSession", ending: Ending,
                winner: str | None) -> "CombatSession":
    from kirby_combat.session.events import EndProposed, make_author_engine
    return _append(session, EndProposed, author=make_author_engine(),
                   ending=Ending(ending).value, winner=winner)


def conclude(session: "CombatSession", ending: Ending,
             verdict_winner: str | None) -> "CombatSession":
    """The stop condition (or a guard) says the fight is over: end it or ask,
    as its terms say. Returns the session unchanged when the GM has already
    declined this exact verdict, or a question is already open."""
    from kirby_combat.session.events import make_author_engine
    if ended(session) is not None or open_proposal(session) is not None:
        return session
    if terms_of(session).end_mode is EndMode.AUTO_STOP:
        return end_fight(session, ending, verdict_winner,
                         author=make_author_engine())
    if (Ending(ending).value, verdict_winner) in declined_verdicts(session):
        return session
    return propose_end(session, ending, verdict_winner)


def answer_end(session: "CombatSession", *, accept: bool,
               gm_id: str) -> "CombatSession":
    """The GM's answer to the open proposal. Yes ends the fight as the GM;
    no records ``EndDeclined`` and the fight carries on."""
    from kirby_combat.session.events import EndDeclined, make_author_gm
    if ended(session) is not None:
        raise ValueError(f"session {session.id!r} has already ended")
    proposal = open_proposal(session)
    if proposal is None:
        raise ValueError(
            f"session {session.id!r}: no end has been proposed, so there is "
            "nothing to answer (the GM ends a fight with call_fight)")
    author = make_author_gm(gm_id)
    if accept:
        return end_fight(session, Ending(proposal.ending), proposal.winner,
                         author=author)
    return _append(session, EndDeclined, author=author,
                   ending=proposal.ending, winner=proposal.winner)


def call_fight(session: "CombatSession", *, gm_id: str) -> "CombatSession":
    """The GM ends the fight now, whatever its terms (a surrender, the
    police arrive). Closes any open proposal."""
    from kirby_combat.session.events import make_author_gm
    return end_fight(session, Ending.CALLED, None, author=make_author_gm(gm_id))


def verdict_of(session: "CombatSession") -> Verdict:
    """What the fight's own stop condition says right now."""
    return Roster(session).decide(condition_for(terms_of(session).stop))


__all__ = [
    "Ending", "EndMode", "FightTerms", "FightTermsMissing", "FirstBlood",
    "GmOnly", "StopKind", "answer_end", "call_fight", "conclude",
    "condition_for", "declined_verdicts", "end_fight", "ended",
    "open_proposal", "propose_end", "state_terms", "terms_of", "verdict_of",
]
