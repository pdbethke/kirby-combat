"""Who cannot be seen, read off the fight's own log.

TWO KINDS OF CONCEALMENT, AND ONLY ONE WAS EVER VISIBLE. Invisibility is
bought on the build, so `perception.invisibility_groups` can read it from
the character at any moment. HIDING is a fact about the FIGHT --- it
happened at a particular Phase, against particular watchers --- and the
only record of it is the event log.

`_resolve_hide` runs the contest properly: Stealth against every watcher's
PER, resolved PER OBSERVER, "because being unseen is not a property of the
hider: one enemy may lose you while another keeps you in view". It writes
the losers to the payload as ``unseen_by``. Nothing ever read that list.
The three lines that build it were its only references in the engine, so:

  * `enumerate_actions` takes a ``concealment`` map and `loop/run.py`
    passed none, leaving the perception gate blind to hiding;
  * `perception.is_surprised` takes ``attacker_hidden`` and no caller
    supplied it, so the one manoeuvre in the game designed to produce
    6E2 p.52's Surprised could never produce it.

A Phase spent Hiding bought a log entry and nothing else.

PAIRWISE, WHICH IS WHY THIS TAKES AN OBSERVER. The map `enumerate_actions`
consumes is flat --- ``{combatant_id: (invisible, hidden)}`` --- but it is
always built for ONE actor's point of view, so answering it from that
observer's side keeps the pairwise truth the contest established instead
of flattening "unseen by somebody" into "unseen".
"""
from __future__ import annotations

from typing import Any

#: What `_resolve_hide` writes, and the key nothing read.
UNSEEN_BY = "unseen_by"


def _hide_results(session) -> list[tuple[str, set[str]]]:
    """Every resolved Hide in this fight, oldest first: (hider, watchers)."""
    out: list[tuple[str, set[str]]] = []
    for event in getattr(session, "event_log", None) or []:
        payload = getattr(event, "result_payload", None)
        if not isinstance(payload, dict) or payload.get("kind") != "hide":
            continue
        author = getattr(getattr(event, "author", None), "id", None)
        if author is None:
            continue
        out.append((author, set(payload.get(UNSEEN_BY) or ())))
    return out


def hidden_from(session, observer_id: str) -> set[str]:
    """Ids this observer has lost track of.

    LAST HIDE WINS, per hider. A second Hide re-runs the contest against
    everyone, so its answer supersedes the first --- including for a
    watcher who had lost him and has now found him again. Reading every
    entry and unioning them would make hiding permanent, which no roll in
    the engine ever undoes.
    """
    latest: dict[str, set[str]] = {}
    for hider, unseen in _hide_results(session):
        latest[hider] = unseen
    return {hider for hider, unseen in latest.items() if observer_id in unseen}


def is_invisible(combatant) -> bool:
    """Whether the build carries any Invisibility at all.

    Deliberately coarse: `perceive` does the per-Sense-Group work, and
    this only answers the yes/no the ``concealment`` map is shaped for.
    """
    from kirby_combat.perception import invisibility_groups

    hero = getattr(combatant, "hero", None)
    if hero is None:
        return False
    return bool(invisibility_groups(hero))


def concealment_for(session, *, observer_id: str) -> dict[str, tuple[bool, bool]]:
    """The ``concealment`` map `enumerate_actions` has always accepted.

    ``{combatant_id: (invisible, hidden)}`` from this observer's point of
    view. Only concealed combatants appear --- an empty map is the honest
    answer for a fight where nobody has hidden and nobody is invisible,
    and it is what every caller got by accident before this existed.
    """
    hidden = hidden_from(session, observer_id)
    out: dict[str, tuple[bool, bool]] = {}
    for combatant_id, combatant in (getattr(session, "combatants", None) or {}).items():
        invisible = is_invisible(combatant)
        concealed = combatant_id in hidden
        if invisible or concealed:
            out[combatant_id] = (invisible, concealed)
    return out


def perceives(session, observer, target, **kwargs: Any) -> bool:
    """Whether `observer` can target `target` right now, hiding included.

    The one place the log's concealment and the build's Invisibility are
    handed to `perception.perceive` together, so callers do not each
    assemble the arguments and each forget a different one.
    """
    from kirby_combat.perception import perceive

    scene = getattr(session, "scene", None)
    conceal = concealment_for(session, observer_id=getattr(observer, "id", ""))
    invisible, hidden = conceal.get(getattr(target, "id", ""), (False, False))
    result = perceive(observer, target, scene,
                      target_invisible=invisible, target_hidden=hidden,
                      **kwargs)
    return bool(result.targetable_physical or result.targetable_mental)
