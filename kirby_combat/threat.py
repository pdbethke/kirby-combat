"""How dangerous is that one? --- the fact a fighter picks a target with.

Every tactic that names a victim used to pick on some single axis of its
own: `keep_range` takes the enemy it most outranges, others take the
nearest or the weakest. None of them asked who is actually dangerous, and
with `target_id` finally reaching the chooser that showed immediately ---
the Earps spent the O.K. Corral shooting the two UNARMED men running
away, because being harmless is exactly what makes you easy to outrange,
while Power Lad tore their brothers apart beside them.

TWO HALVES, because a fighter knows two different things.

**The menace floor --- what he can see standing there.** A seven-foot
horror with claws is visibly dangerous before it does anything, and a
model that only learns from experience makes every fight start stupid.
Read in DAMAGE CLASSES, which is the game's own unit for "how hard does
that hit" (6E1 p.97: a Killing die is three DCs where a Normal die is
one), plus PRE in the units the book itself uses for it --- 6E2 p.137
throws one Presence die per 5 PRE. PRE is the characteristic for being
imposing and nothing else, so it belongs here.

**Observed harm --- what he has watched him do.** Folded from the
session's own event log, which is the half that honours the rule
perception already enforces: act on what happened in front of you, not on
what the character sheet says. A Presence Attack that landed counts here
too --- 6E2 p.137 makes it an attack on everyone who can hear it, and it
is the loudest thing anybody in that lot could witness.

WHAT THIS IS NOT. Not a to-hit calculation and not a "who will I beat"
prediction. It is one number meaning "how much of a problem is that
one", for a tactic to weigh against everything else it cares about. A
tactic is still free to shoot someone else for its own reasons.
"""
from __future__ import annotations

from typing import Any

#: 6E1 p.97. A Killing die is worth three damage classes against a Normal
#: die's one, which is why counting dice alone calls 6d6 of claws and a
#: 6d6 blast the same threat. They are not the same threat.
DC_PER_KILLING_DIE = 3
DC_PER_NORMAL_DIE = 1

#: 6E2 p.137: "a character rolls 1d6 for every 5 points of PRE he has".
#: Presence enters the sum in its own native unit rather than a weight
#: invented here.
PRE_PER_DIE = 5.0

#: What a landed Presence Attack adds. A JUDGEMENT, and a deliberately
#: blunt one: the tiers already differ in what they DO to the target
#: (6E2 p.138 --- impressed, very impressed, awed, cowed), and this only
#: needs to say "that one made an impression on people".
PRESENCE_WITNESSED = 3.0

#: STUN is worth less than BODY as evidence of danger: a man who has been
#: knocked about recovers, a man who has been opened up does not.
STUN_PER_BODY = 5.0


def _damage_classes(combatant: Any) -> float:
    """The hardest single hit this fighter visibly carries, in DCs."""
    best = 0.0
    for attack in (getattr(combatant, "attacks", None) or []):
        dice = float(getattr(attack, "damage_dice", 0) or 0)
        killing = (getattr(attack, "damage_type", "") or "") == "killing"
        best = max(best, dice * (DC_PER_KILLING_DIE if killing
                                 else DC_PER_NORMAL_DIE))
    return best


def _presence(combatant: Any) -> float:
    try:
        return float(getattr(combatant.combat_stats(), "pre", 0) or 0)
    except Exception:                                   # noqa: BLE001
        return 0.0


def menace(combatant: Any) -> float:
    """What can be read off a fighter without watching him fight."""
    return _damage_classes(combatant) + _presence(combatant) / PRE_PER_DIE


def harm_witnessed(session: Any, ids: set[str]) -> dict[str, float]:
    """What each of `ids` has been SEEN to do, from the event log.

    Attribution needs both halves of the pair the resolvers emit:
    `ActionDeclared` carries the actor, `ActionResolved` carries the
    outcome, and they are joined by `declaration_event_id`. Reading only
    the resolutions would give a log full of damage nobody did.
    """
    out: dict[str, float] = {i: 0.0 for i in ids}
    log = list(getattr(session, "event_log", None) or [])
    actor_of: dict[str, str] = {}
    for event in log:
        kind = getattr(event, "kind", "")
        if kind == "ActionDeclared":
            actor_of[getattr(event, "id", "")] = getattr(event, "combatant_id", "")
        elif kind == "ActionResolved":
            who = actor_of.get(getattr(event, "declaration_event_id", ""), "")
            if who not in out:
                continue
            payload = getattr(event, "result_payload", None) or {}
            out[who] += float(payload.get("body_dealt", 0) or 0)
            out[who] += float(payload.get("stun_dealt", 0) or 0) / STUN_PER_BODY
        elif kind == "PresenceApplied":
            who = getattr(event, "attacker_id", "")
            if who in out:
                out[who] += PRESENCE_WITNESSED
    return out


def threat_map(enemies: list, session: Any = None) -> dict[str, float]:
    """`enemy id -> how much of a problem that one is`.

    Answerable with no session at all --- most fights are driven without
    one in hand, and a fighter can always see who is holding the axe.
    """
    ids = {getattr(e, "id", "") for e in enemies}
    seen = harm_witnessed(session, ids) if session is not None else {}
    return {getattr(e, "id", ""): menace(e) + seen.get(getattr(e, "id", ""), 0.0)
            for e in enemies}
