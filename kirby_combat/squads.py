"""Squads and who leads them (squad tactics spec, section 4).

A fight's seating may declare squads: each combatant's `squad` names the one
he fights in, or is None for a man in no squad. The GM declares them, like
`minor_hits`; nothing is inferred from the roster and there is no default
squad size. A squad is a name on a SIDE: the same name on two sides is two
squads.

THE LEADER is decided by the engine from the builds, so that anyone watching
can see who comes out on top. RULING (no book page; HERO has no squad
leader): among the members still standing, the best Tactics roll leads
(`skill_roll_value("TACTICS")`; a man without the Skill ranks below any
roll), then the higher INT, then the higher PRE, then the member seated
first. A contested roll is the alternative, which adds dice and no
difference anybody could see.

When the leader goes down the rule is applied again at once to the men still
standing, in the same step, so `SquadLeaderNamed` follows the row that downed
him. The new leader can give orders on his own next Phase.

"Standing" is the Roster's: not `is_down` (6E1 p.421) and not gone from the
field.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

#: Below any roll a man can have, for a member with no Tactics.
_NO_TACTICS = -1


@dataclass(frozen=True)
class Squad:
    """A named squad on one side, its members in seating order."""

    name: str
    side: str
    member_ids: tuple[str, ...]


def squads_of(session: Any) -> tuple[Squad, ...]:
    """Every squad the seating declares, grouped by ``(side, squad)``.

    In the order each squad's first member was seated; members in seating
    order. A squad name used on two sides is two squads.
    """
    from kirby_combat.side import Side

    groups: dict[tuple[str, str], list[str]] = {}
    for combatant in session.combatants.values():
        name = getattr(combatant, "squad", None)
        if name is None:
            continue
        groups.setdefault((Side.of(combatant).id, name), []).append(combatant.id)
    return tuple(Squad(name=name, side=side, member_ids=tuple(ids))
                 for (side, name), ids in groups.items())


def leader_rule(session: Any, squad: Squad) -> str | None:
    """Who should lead ``squad`` now: the best of the men still standing by
    Tactics, then INT, then PRE, then seating order; None if none stand."""
    up = _standing_ids(session)
    best: str | None = None
    best_key: tuple[int, int, int] | None = None
    for member_id in squad.member_ids:
        if member_id not in up:
            continue
        member = session.combatants[member_id]
        tactics = member.skill_roll_value("TACTICS")
        key = (_NO_TACTICS if tactics is None else int(tactics),
               int(member.int_), int(member.pre))
        # Strictly greater, so a full tie keeps the man seated first.
        if best_key is None or key > best_key:
            best, best_key = member_id, key
    return best


def _standing_ids(session: Any) -> set[str]:
    from kirby_combat.roster import Roster

    return {i for ids in Roster(session).standing.values() for i in ids}


def _latest_naming(session: Any, squad_name: str, side: str):
    for event in reversed(session.event_log):
        if (getattr(event, "kind", "") == "SquadLeaderNamed"
                and event.squad == squad_name and event.side == side):
            return event
    return None


def leader_of(session: Any, squad_name: str, side: str) -> str | None:
    """The squad's leader as the log last named him; None if nobody leads it
    (none standing, or no `SquadLeaderNamed` yet)."""
    named = _latest_naming(session, squad_name, side)
    return None if named is None else named.leader_id


def name_leaders(session: Any) -> Any:
    """Write a `SquadLeaderNamed` for each squad whose leader is not what the
    rule now says, and return the session. Squads that are unchanged write
    nothing, so an all-down squad records ``leader_id=None`` once.

    Called when the fight begins and at the end of every Phase and step
    (`loop/run.py`). The reason is "fight began" for a squad never named,
    else "<old id> went down".
    """
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import SquadLeaderNamed, make_author_engine

    for squad in squads_of(session):
        named = _latest_naming(session, squad.name, squad.side)
        leader = leader_rule(session, squad)
        if named is None:
            reason = "fight began"
        elif named.leader_id is None or named.leader_id == leader:
            # Nobody led and the squad has not been re-formed, or he leads.
            continue
        elif named.leader_id in _standing_ids(session):
            # He is still up: the Skill or INT moving under him (a Drain) is
            # not a reason to take the squad from him.
            continue
        else:
            reason = f"{named.leader_id} went down"
        session = apply_event(session, SquadLeaderNamed(
            id=str(uuid.uuid4()), session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc), author=make_author_engine(),
            squad=squad.name, side=squad.side, leader_id=leader, reason=reason,
        ))
    return session
