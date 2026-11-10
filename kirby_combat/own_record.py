"""What his own last actions did, as he saw them.

FOUND 2026-11-10: Plague fired his Killing Attack nine times at a dodging
agent and missed every time, and made three group Presence Attacks of which
the last two did nothing --- and his page never said so. Nothing on it
recorded what his own actions had done, so whatever the doctrine said last
Phase it said again (combat-decisions spec, Phase 7: the next page shows
"what happened, as she can judge it"; PokéLLMon's feedback from the last
turn).

FACTS, NOT ADVICE. This says what happened; it never says what to do.

WHAT HE SAW. A miss and how wide (the margin is the roll he made against
the number he needed; on a JUDGED page as words, since the number would
give away the target's DCV), what a hit visibly did (the words
`judgement` uses for any blow: he staggered, he dropped), a Presence
Attack's effect on each man (they react visibly), and a run of misses on
one man.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.loop.chooser import PhaseSituation

#: How many of his own last actions are listed. The page-size reason
#: `brief_detail.MAX_LISTED` gives; the newest are the ones that say how
#: it is going.
MAX_OWN_LISTED = 4

#: A run of misses on one man worth saying as a run. Two is a pattern
#: starting; one is a miss.
MISS_RUN = 2

#: How a miss's margin reads on a judged page, widest first. A RULING on
#: words: the margin is what he rolled against what he needed, which he
#: knows; the number itself would tell him the enemy's DCV.
_MISS_WORDS = ((6, "missed badly"), (3, "missed clearly"), (1, "just missed"))


def _miss_words(margin: int) -> str:
    gap = -int(margin)
    for at_least, words in _MISS_WORDS:
        if gap >= at_least:
            return words
    return "just missed"


def _name(session: Any, combatant_id: str | None) -> str:
    c = session.combatants.get(combatant_id) if combatant_id else None
    return getattr(c, "name", None) or str(combatant_id or "someone")


def own_actions(session: Any, actor_id: str) -> list[dict]:
    """His resolved actions, oldest first: ActionResolved authored by him,
    not a lingering dose (that is the power working, not his action) and
    not joining a Coordinated attack (said by the attack that follows)."""
    out = []
    for evt in session.event_log:
        if getattr(evt, "kind", None) != "ActionResolved":
            continue
        author = getattr(evt, "author", None)
        if getattr(author, "type", None) != "combatant" or getattr(author, "id", None) != actor_id:
            continue
        payload = getattr(evt, "result_payload", None) or {}
        if payload.get("lingering_id") or payload.get("kind") in ("coordinate", None):
            continue
        # A burst is recorded twice: its summary (with ``hits``) and each
        # landing. One burst is one action.
        if payload.get("kind") in ("autofire", "autofire_spray") and "hits" not in payload:
            continue
        out.append(payload)
    return out


def _presence_line(session: Any, payload: dict) -> str:
    effects = payload.get("effects") or {}
    if not effects:
        target = _name(session, payload.get("target_id"))
        effect = payload.get("effect") or payload.get("tier") or "no visible effect"
        return f"Presence Attack on {target}: {str(effect).replace('_', ' ')}"
    tally: dict[str, int] = {}
    for tier in effects.values():
        key = str(tier).replace("_", " ")
        tally[key] = tally.get(key, 0) + 1
    if set(tally) == {"no effect"}:
        return f"group Presence Attack on {len(effects)}: no effect on any of them"
    parts = ", ".join(f"{tier} {n}" for tier, n in sorted(tally.items()))
    return f"group Presence Attack on {len(effects)}: {parts}"


def _line(session: Any, payload: dict, *, judged: bool, unseen: frozenset = frozenset()) -> str:
    from kirby_combat.judgement import _landed_line

    kind = payload.get("kind")
    if kind in ("presence_attack", "presence_attack_group"):
        return _presence_line(session, payload)
    what = payload.get("power_name") or str(kind).replace("_", " ")
    target_id = payload.get("target_id")
    at = f" at {_name(session, target_id)}" if target_id else ""
    if "hit" not in payload:
        return f"{what}{at}"
    if payload.get("kind") in ("autofire", "autofire_spray") and payload.get("hit"):
        n = int(payload.get("hits") or 0)
        return f"{what}{at}: burst, {n} hit{'s' if n != 1 else ''}"
    if not payload.get("hit"):
        margin = payload.get("margin")
        if margin is None:
            return f"{what}{at}: missed"
        if judged:
            return f"{what}{at}: {_miss_words(int(margin))}"
        return f"{what}{at}: missed by {-int(margin)}"
    if payload.get("damage_over_time"):
        return f"{what}{at}: hit; it works on him over time"
    if target_id in unseen:
        # He knows his blow connected; what it did to a man he cannot see
        # now is not his to know (perception's hard rule: nothing on the
        # page he could not judge with his own senses).
        return f"{what}{at}: hit"
    seen = _landed_line(payload, target_id).split("; ", 1)[-1] if target_id else ""
    if not judged and ("stun_dealt" in payload or "body_dealt" in payload):
        seen += (f" ({int(payload.get('stun_dealt') or 0)} STUN, "
                 f"{int(payload.get('body_dealt') or 0)} BODY through)")
    return f"{what}{at}: hit; {seen}" if seen else f"{what}{at}: hit"


def own_record_lines(situation: "PhaseSituation") -> list[str]:
    """His last actions this fight and what they did, then any run of
    misses on one man. Empty before he has done anything."""
    from kirby_combat.brief_detail import page_is_judged

    session = situation.session
    if session is None:
        return []
    actor_id = str(situation.actor.id)
    mine = own_actions(session, actor_id)
    if not mine:
        return []
    judged = page_is_judged(situation)
    from kirby_combat.brief_detail import sightings

    seen = sightings(situation)
    unseen = frozenset(i for i, s in seen.items() if not s.perceived)
    lines = [_line(session, p, judged=judged, unseen=unseen)
             for p in mine[-MAX_OWN_LISTED:]]
    if len(mine) > MAX_OWN_LISTED:
        lines.insert(0, f"(and {len(mine) - MAX_OWN_LISTED} earlier)")
    # A RUN OF MISSES on one man, counted back from the latest attack on him.
    runs: dict[str, int] = {}
    closed: set[str] = set()
    for payload in reversed(mine):
        target = payload.get("target_id")
        if not target or target in closed or "hit" not in payload:
            continue
        if payload.get("hit"):
            closed.add(target)
        else:
            runs[target] = runs.get(target, 0) + 1
    for target, n in runs.items():
        if n >= MISS_RUN:
            lines.append(f"you have missed {_name(session, target)} {n} times running")
    return lines
