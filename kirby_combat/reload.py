"""Change Clips: the reload a power bought with Clips allows (6E1 p.371).

THE RULES. 6E1 p.371: "This represents a power whose Charges are broken down
into several smaller 'clips' of fewer Charges ... It takes a Full Phase for a
character to change Clips (unless he succeeds with a Fast Draw roll, see 6E1
76)." 6E1 p.76: "If a character uses a weapon that has Charges bought with
Clips (such as most firearms), a successful Fast Draw roll also allows him to
change Clips as a Half Phase Action."

A POWER WITH PLAIN CHARGES HAS ONE CLIP and no reload in the fight: the
Equipment Guide (p.58) says "each gun comes with one 'clip' of ammunition
unless noted otherwise", and Charges come back with the day, or with a box of
shells from the gun store (EG p.69), not between Phases.

The common case is a hero with Charges and Clips --- "2 clips of 12 Charges"
--- who until this ran his first clip dry and then had no attack at all.

NOT BUILT: Increased Reloading Time (6E1 p.371's table: 2 Full Phases, a
Turn, a Minute ...). That reload spans Phases during which "he can take no
other Actions", which this loop cannot yet hold a man to, so such a power is
offered no reload rather than a wrong one.

The Fast Draw reload is rolled; a made roll takes a Half Phase and a missed
one the Full Phase (the clip is changed either way: "unless he succeeds"
names the time, not the reload). Its time is read off the row it writes
(`action_time.rolled_time`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from kirby_combat.loop.registry import ResolvedAction, UnresolvableAction, _events_since, resolves

RELOAD, FAST_RELOAD = "reload", "fast_reload"
KINDS = frozenset({RELOAD, FAST_RELOAD})


def _charged_powers(actor: Any) -> list:
    from kirby_combat.identity import build_in_play

    build = build_in_play(actor)
    return [*(getattr(build, "powers", None) or []), *(getattr(build, "equipment", None) or [])]


def reload_offers(session, actor: Any) -> list:
    """A fresh clip for each pool he has fired from and has clips left for."""
    from kirby_combat.charges import charge_pool, clips_changed, clips_on, increased_reload, spent_charges
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.holster import has_fast_draw

    spent = spent_charges(session, actor.id)
    fast = has_fast_draw(actor)
    out: list = []
    seen: set[str] = set()
    for power in _charged_powers(actor):
        pool = charge_pool(power)
        if pool is None or pool[0] in seen:
            continue
        seen.add(pool[0])
        owner = power if pool[0] == str(getattr(power, "id", "")) else getattr(power, "parent", power)
        clips = clips_on(owner)
        if clips <= 1 or increased_reload(owner) is not None:
            continue
        if clips_changed(session, actor.id, pool[0]) >= clips - 1:
            continue                       # no clips left to put in
        if spent.get(pool[0], 0) <= 0:
            continue                       # this clip is still full
        name = getattr(owner, "name", None) or getattr(owner, "alias", "") or pool[0]
        left = pool[1] - spent.get(pool[0], 0)
        kind = FAST_RELOAD if fast else RELOAD
        out.append(LegalAction(
            action_id=f"{kind}:{pool[0]}", kind=kind, target_id=None,
            power_xmlid=None, power_name=name,
            summary=(f"Change Clips on your {name} ({left} of {pool[1]} left, "
                     f"{clips - 1 - clips_changed(session, actor.id, pool[0])} spare): "
                     + ("a Fast Draw roll makes it a Half Phase, a miss the Full Phase (6E1 p.76)"
                        if fast else "a Full Phase (6E1 p.371)"))))
    return out


@resolves(RELOAD, FAST_RELOAD)
def _resolve_reload(session, actor, action, *, template, roller) -> ResolvedAction:
    from kirby_combat.holster import FAST_DRAW_SKILL
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ClipChanged, make_author_combatant
    from kirby_combat.wounds import _made

    pool_id = action.action_id.split(":", 1)[1]
    if not any(o.action_id == action.action_id for o in reload_offers(session, actor)):
        raise UnresolvableAction(action.kind, action.action_id)
    took, roll, needed = "full", 0, 0
    if action.kind == FAST_RELOAD:
        needed = int(actor.skill_roll_value(FAST_DRAW_SKILL))
        roll = sum(roller.roll_dice(3, 6))
        took = "half" if _made(roll, needed) else "full"
    after = apply_event(session, ClipChanged(
        id=str(uuid.uuid4()), session_id=session.id, sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_combatant(actor.id),
        combatant_id=actor.id, pool_id=pool_id, took=took, fast_draw_roll=roll,
        needed=needed))
    payload = {"pool_id": pool_id, "took": took, "fast_draw_roll": roll, "needed": needed}
    return ResolvedAction(session=after, kind=action.kind, action_id=action.action_id,
                          result=payload, events=_events_since(session, after))
