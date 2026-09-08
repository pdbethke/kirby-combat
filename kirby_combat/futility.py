"""Blows that landed and did nothing --- the evidence a fighter has.

Seven armed men emptied revolvers into Power Lad for twenty-eight Phases
at the O.K. Corral. Every shot that LANDED got nothing through his 25
rPD, and none of them ever tried anything else, because nothing in
twenty-two tactics says "that is not working".

It looks like a morale gap and it is not one. HERO gives an individual no
morale stat --- PRE is the stat, and 6E2 p.140's worked example says so
outright: Howler's "demoralized henchmen are about to run" and she fixes
it with a Presence Attack. But terror scales with the terrifier's PRE,
and a quiet monster will never break anybody. What breaks them is
arithmetic they can do themselves.

A MISS PROVES NOTHING. You might hit next time, and a doctrine built on
misses would have men fleeing every ordinary fight. A blow that LANDED
and did no BODY proves something exact: what you are holding cannot hurt
what you are pointing it at. That is the fact this counts, per target,
from the session's own log --- and it is precisely what the man swinging
would know, which is the same standard perception already holds the AI
to.
"""
from __future__ import annotations

from typing import Any


def futile_hits(session: Any, attacker_id: str,
                *, also: tuple[str, ...] = ()) -> dict[str, int]:
    """`target id -> landed blows that did no BODY`.

    `also` pools a SIDE's evidence with the actor's own. PeterB, 2026-09-08:
    "the cowboys and the earps qualify as teams". A man who lands one blow
    for nothing has bad luck; three men who land one each have a fact
    between them, and in a 5.5m lot they watched each other do it.

    That correction came from a measurement. At the Corral there were
    nineteen shots at Power Lad, FIVE of them landing, and no individual
    ever reached three -- OCV 5 against DCV 6 means they mostly miss. The
    evidence was in the fight the whole time and no single man held enough
    of it. This module first said another man's failure was "an opinion
    rather than evidence", which is wrong for people fighting shoulder to
    shoulder.

    Not the metagaming perception forbids, either: watching a bullet
    strike a man and do nothing is an observation. And the pool is the
    SIDE, never the room -- an enemy's failure teaches you nothing, since
    he is a man you are trying to kill.

    Attribution needs both events the resolvers emit --- `ActionDeclared`
    carries who, `ActionResolved` carries what, joined on
    `declaration_event_id`. Targets that hurt are absent rather than
    zero, so the mapping reads as "what is not working".
    """
    out: dict[str, int] = {}
    log = list(getattr(session, "event_log", None) or [])
    watchers = {attacker_id, *also}
    mine: set[str] = set()
    for event in log:
        kind = getattr(event, "kind", "")
        if kind == "ActionDeclared":
            if getattr(event, "combatant_id", "") in watchers:
                mine.add(getattr(event, "id", ""))
        elif kind == "ActionResolved":
            if getattr(event, "declaration_event_id", "") not in mine:
                continue
            payload = getattr(event, "result_payload", None) or {}
            if not payload.get("hit"):
                continue
            if float(payload.get("body_dealt", 0) or 0) > 0:
                continue
            target = payload.get("target_id") or ""
            if target:
                out[target] = out.get(target, 0) + 1
    return out


def anything_working(session: Any, attacker_id: str) -> bool:
    """Has this fighter got BODY through ANYBODY?

    A man hitting one target uselessly has no reason to leave a fight he
    is winning against somebody else, which is the difference between
    "this one is invulnerable" and "I am beaten".
    """
    log = list(getattr(session, "event_log", None) or [])
    mine: set[str] = set()
    for event in log:
        kind = getattr(event, "kind", "")
        if kind == "ActionDeclared":
            if getattr(event, "combatant_id", "") == attacker_id:
                mine.add(getattr(event, "id", ""))
        elif kind == "ActionResolved":
            if getattr(event, "declaration_event_id", "") not in mine:
                continue
            payload = getattr(event, "result_payload", None) or {}
            if float(payload.get("body_dealt", 0) or 0) > 0:
                return True
    return False
