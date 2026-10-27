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

#: The payload kind that ends a man's Hide: he attacked out of it.
HIDE_BROKEN = "hide_broken"

#: Every action kind that is an OVERT ATTACK and so gives a hider away.
#:
#: RULING (6E2 leaves this to the GM, and so it is recorded rather than
#: cited as RAW): a Hide ends when the hider attacks. 6E2 p.52 names "a
#: heretofore unseen sniper fires at the character" as the Surprise a hidden
#: man earns --- the shot is what makes him seen, and the same page has a
#: man revealing his powers spend his Surprise in the revealing. 6E1 p.127
#: charges a hider -1 to his Stealth roll per 10 Active Points of an Obvious
#: Power he uses, which no attack this engine resolves survives for long.
#: The one attack out of hiding is still Surprised (the break is recorded
#: AFTER it resolves); hiding again is a new Hide.
#:
#: The list is the parked kirby-api driver's overt-attack list
#: (deleted in kirby-api 70ad60f): damaging attacks and offensive
#: maneuvers, movement-strikes, Presence and mental attacks. Movement,
#: Dodge, Block, Set, Recover, Hold, Haymaker (a declaration), Hide itself
#: and social or utility actions leave a Hide intact.
REVEALING_KINDS = frozenset({
    "attack", "strike", "grab", "trip", "disarm", "push", "spread",
    "throw", "throw_object", "maneuver", "move_strike", "move_by",
    "move_through", "rapid_fire", "multiple_attack", "sweep",
    "presence_attack", "presence_attack_group", "attack_construct",
    "mental_blast", "mind_control", "mental_illusion", "entangle",
    "mental_entangle", "telepathy", "drain", "dispel", "flash",
    "reposition_strike", "autofire", "autofire_spray",
})


def _hide_results(session) -> list[tuple[str, set[str]]]:
    """Every resolved Hide in this fight, oldest first: (hider, watchers).

    A broken Hide is an entry with no watchers: from then on nobody has
    lost him, until he Hides again.
    """
    out: list[tuple[str, set[str]]] = []
    for event in getattr(session, "event_log", None) or []:
        payload = getattr(event, "result_payload", None)
        if not isinstance(payload, dict):
            continue
        kind = payload.get("kind")
        if kind not in ("hide", HIDE_BROKEN):
            continue
        author = getattr(getattr(event, "author", None), "id", None)
        if author is None:
            continue
        unseen = set(payload.get(UNSEEN_BY) or ()) if kind == "hide" else set()
        out.append((author, unseen))
    return out


def is_hidden_from_anyone(session, combatant_id: str) -> bool:
    """Whether any watcher has lost track of this man right now."""
    latest: set[str] = set()
    for hider, unseen in _hide_results(session):
        if hider == combatant_id:
            latest = unseen
    return bool(latest)


def break_hide(session, combatant_id: str, *, by_kind: str):
    """End his Hide if ``by_kind`` is an overt attack. See `REVEALING_KINDS`.

    Recorded as its own row, authored by the hider, so a fight rebuilt from
    its log un-hides him at the same moment the fight that ran did.
    Returns the session untouched when there is nothing to break.
    """
    import uuid
    from datetime import datetime, timezone

    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ActionResolved, make_author_combatant

    if by_kind not in REVEALING_KINDS or not is_hidden_from_anyone(session, combatant_id):
        return session
    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(combatant_id),
        declaration_event_id="",
        result_payload={"kind": HIDE_BROKEN, "by_kind": by_kind},
    ))


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


def perceives(session, observer, target, *, roller, **kwargs: Any) -> bool:
    """Whether `observer` can target `target` right now, hiding included.

    The one place the log's concealment and the build's Invisibility are
    handed to `perception.perceive` together, so callers do not each
    assemble the arguments and each forget a different one.

    IT ALSO CARRIES THE OBSERVER'S FLASH, AND FOR THE SAME REASON. A
    caller that reached `perceive` through here still had to remember
    ``observer_flashed_groups`` on its own, which is the same forgetting
    one argument at a time this door exists to stop --- and it was a
    forgetting with teeth, because a Flash is the one blinding that needs
    no geometry and so is the only one a scene-less fight can have. The
    read is `Flash.is_flashed`, the engine's own fold of the log; nothing
    is recomputed here.

    AND IT DOES NOT FAIL OPEN. `perceive` asks the observer for
    `senses()`, which only a build-backed combatant has. A flat stat
    block is handed 6E2 p.9's normal human by `as_sensing_observer` ---
    the same grounding `sense_penalties.cannot_perceive` uses, shared
    rather than copied --- so a stat block Flashed in the Sight Group is
    blind here rather than silently sighted.

    NOT ALWAYS A READ, WHICH IS WHY `roller` IS REQUIRED. `perceive` rolls
    in exactly two places: the PER roll for an Invisible target's Fringe
    within 2 m, and a Hidden target's opposed Stealth contest. Every other
    pair is deterministic. `perceive` builds its own `RandomRoller` when
    handed none, so a caller that omitted it would get a different answer
    for those two pair kinds on every call --- which is fine for a
    one-shot question and fatal for anything replayed. There is no
    default here: the caller says which roller, or the call does not
    happen.

    `sense_penalties.cannot_perceive` is a NARROWER question and stays its
    own predicate: it asks only `targetable_physical`, because a CV
    penalty is about aiming a physical attack, where this asks whether the
    target can be reached by any sense at all.
    """
    from kirby_combat.actions.flash import Flash
    from kirby_combat.perception import perceive
    from kirby_combat.sense_penalties import as_sensing_observer

    scene = getattr(session, "scene", None)
    conceal = concealment_for(session, observer_id=getattr(observer, "id", ""))
    invisible, hidden = conceal.get(getattr(target, "id", ""), (False, False))
    _, flashed = Flash.is_flashed(session, getattr(observer, "id", ""))
    kwargs.setdefault("observer_flashed_groups", frozenset(flashed))
    result = perceive(as_sensing_observer(observer), target, scene,
                      target_invisible=invisible, target_hidden=hidden,
                      roller=roller, **kwargs)
    return bool(result.targetable_physical or result.targetable_mental)
