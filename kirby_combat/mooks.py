"""Minor NPCs: the book's three rules for making them fall like extras.

6E2 p.121-122 offers optional rules "to make a game a little more like
novels and movies", which "should only apply to minor or trivial NPCs;
major enemies and villains should function in combat just like PCs do":

* ``minor_dead_at_zero_body``: "Once a minor enemy hits 0 BODY, he falls
  over dead."
* ``minor_stunned_is_dead``: "any time a minor NPC becomes Stunned by a
  Normal Damage or Killing Damage attack, he's not Stunned - he's dead."
* ``minor_hit_counting``: the GM does not "worry about the exact STUN and
  BODY a minor enemy has - they simply decide how many hits it takes to
  kill him. The weakest are one-hit wonders: a single successful Attack
  Roll against them kills them ... a two-hit foe takes two successful
  Attack Rolls to kill, or only a single Attack Roll that's made by 2 or
  more". A hit made by N or more counts as N (at least 1).

A minor NPC is a combatant with ``minor_hits`` set (the GM's call when he
seats the fight); which rules apply is the campaign template's.

RULINGS, stated:

* An attack counts for these rules when it does Normal or Killing damage
  (``damage_type``), as the Stunned rule says in so many words; a Mental
  Blast, an Entangle or a Drain does not.
* Under hit counting his STUN and BODY are still rolled and folded, as the
  book has the players keep rolling damage "to disguise what he's doing",
  so he can still be knocked out by them. What the rule adds is the death.
  The book's "an especially good roll ... may [count as] the Attack Roll
  by 1 or 2 points more" is the GM's discretion and is not applied.
"""
from __future__ import annotations

from typing import Any

#: The damage the minor-NPC rules count (6E2 p.122: "a Normal Damage or
#: Killing Damage attack").
_COUNTED_DAMAGE = frozenset({"normal", "killing"})


def _killed_already(session: Any, combatant_id: str) -> bool:
    return any(getattr(e, "kind", "") == "MinorFoeKilled"
               and e.combatant_id == combatant_id for e in session.event_log)


def _attacks_on(session: Any, combatant_id: str):
    for e in session.event_log:
        if getattr(e, "kind", "") != "ActionResolved":
            continue
        payload = getattr(e, "result_payload", None) or {}
        if (payload.get("target_id") == combatant_id
                and payload.get("damage_type") in _COUNTED_DAMAGE):
            yield e, payload


def why_dead(session: Any, combatant_id: str) -> tuple[str, str] | None:
    """``(rule, cause event id)`` if a minor-NPC rule has killed him, else
    None. Reads the log and his vitals; writes nothing."""
    template = session.template
    combatant = session.combatants.get(combatant_id)
    hits_to_kill = getattr(combatant, "minor_hits", None)
    if combatant is None or hits_to_kill is None:
        return None
    if template.minor_dead_at_zero_body and int(combatant.state.current_body) <= 0:
        return "zero_body", ""
    landed = 0
    for event, payload in _attacks_on(session, combatant_id):
        if template.minor_stunned_is_dead and "Stunned" in (payload.get("status_changes") or ()):
            return "stunned", event.id
        if template.minor_hit_counting and payload.get("hit") is True:
            landed += max(1, int(payload.get("margin") or 0))
            if landed >= int(hits_to_kill):
                return "hits", event.id
    return None


def check_mooks(session: Any) -> Any:
    """Write a `MinorFoeKilled` for each minor NPC a rule has killed and no
    row says so yet. Called at the end of every Phase (`loop/run.py`)."""
    import uuid
    from datetime import datetime, timezone

    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import MinorFoeKilled, make_author_engine

    for cid in list(session.combatants):
        if _killed_already(session, cid):
            continue
        dead = why_dead(session, cid)
        if dead is None:
            continue
        rule, cause = dead
        session = apply_event(session, MinorFoeKilled(
            id=str(uuid.uuid4()), session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc), author=make_author_engine(),
            combatant_id=cid, rule=rule, cause_event_id=cause,
        ))
    return session
