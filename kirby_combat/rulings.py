"""GM rulings: what the table has ruled, and what it takes off the menu.

A RULING is one named fact with the GM's own sentence. Its subject is a
fighter (a ``BodyFact``: "no lungs") or one of his powers (a
``DeliveryRoute``: "delivered by breath"). The fight is handed them once,
as it starts: one `RulingsStated` row per fighter, folded from the log, so
a replay applies the same rulings the live fight did. A GM's edit mid-fight
applies from the next fight.

A RULING ONLY TAKES AWAY WHAT CANNOT HAPPEN. It never grants points, powers
or defences, so it stays out of costing and out of the cost oracle's reach.
The vocabulary is closed and grows case by case: a new fact is one enum
member, one row in ``CLOSES`` if it closes a route, and a test. A fact no
rule reads yet is still stored and still shown; it changes nothing in the
fight. Free text is never parsed: a misread would silently change a fight.

THE GATE (`rulings_gate`). An offer whose power travels by routes reaches a
target only if at least one of them is open on him. A route is closed by a
body fact (``CLOSES``) or by his build: Life Support's Self-Contained
Breathing closes breath (6E1 p.247), read off the build in play, so a
power bought Only In Hero ID protects only the Hero (6E1 p.388,
`identity.build_in_play`). An offer whose every route is closed is not
offered: the menu is how this engine enforces every "cannot affect"
(`desolidification.across_the_line`, perception), and `loop.validate_choice`
refuses anything not on it, so a withheld offer cannot arrive from a seat, a
player or a replay. What the gate removed, and why, goes on
`PhaseSituation.withheld` for the page and the app to read.

RULINGS (each a reading, not a quote):

  * A partly closed set of routes changes nothing: an offer with one open
    route is offered and resolves exactly as it would unruled. A ruling
    never alters dice or effect.
  * A ruling on a Multipower or VPP covers every slot in it. The routes are
    read off the offer's source power first, then up through its
    ``parent_id``s; the nearest purchase with a route ruling decides, so a
    ruling on one slot is read before one on its framework.
  * An Area attack catching a man by the way is not gated here (open, as
    for Desolidification).
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.session.combat_session import CombatSession


class BodyFact(str, Enum):
    """What the GM has ruled a body lacks. Closed; grown case by case."""

    NO_LUNGS = "no_lungs"
    NO_SKIN = "no_skin"
    NO_ORGANS = "no_organs"


class DeliveryRoute(str, Enum):
    """How a power gets into a body. Declaration order is reading order."""

    BREATH = "breath"
    SKIN = "skin"
    INGESTION = "ingestion"


#: Which route each body fact closes. A fact absent from this table closes
#: nothing (yet) and is only shown.
CLOSES: Mapping[BodyFact, DeliveryRoute] = {
    BodyFact.NO_LUNGS: DeliveryRoute.BREATH,
    BodyFact.NO_SKIN: DeliveryRoute.SKIN,
    BodyFact.NO_ORGANS: DeliveryRoute.INGESTION,
}

#: What a closed breath route is put down to when his build closed it.
SELF_CONTAINED_BREATHING = "Self-Contained Breathing"

_FACTS = frozenset(f.value for f in BodyFact)
_ROUTES = frozenset(r.value for r in DeliveryRoute)


@dataclass(frozen=True)
class Ruling:
    """One fact the GM has ruled, with his own sentence.

    ``power_id`` None: a fact about the fighter's body, and ``fact`` is a
    `BodyFact` value. Otherwise the build object's HD ``ID`` (a framework's
    covers its slots), and ``fact`` is a `DeliveryRoute` value. Anything
    else is refused here, so no unread string reaches a fight.
    """

    power_id: str | None
    fact: str
    sentence: str

    def __post_init__(self) -> None:
        allowed, what = ((_FACTS, "BodyFact") if self.power_id is None
                         else (_ROUTES, "DeliveryRoute"))
        if self.fact not in allowed:
            raise ValueError(
                f"ruling fact {self.fact!r} is not a {what} "
                f"({', '.join(sorted(allowed))}); a ruling about "
                f"{'a body' if self.power_id is None else 'a power'} names one")
        if self.power_id is not None and not self.power_id:
            raise ValueError("a ruling's power_id is an HD ID or None, not ''")
        if not self.sentence.strip():
            raise ValueError("a ruling carries the GM's own sentence; it is empty")


@dataclass(frozen=True)
class Withheld:
    """An offer a gate took off the menu, and the reason, for the page."""

    action_id: str
    summary: str
    reason: str


def state_rulings(session: CombatSession, combatant_id: str,
                  rulings: Sequence[Ruling]) -> CombatSession:
    """Put one fighter's rulings on the log (`RulingsStated`).

    Once per fighter per fight, as the fight starts: `apply_event` refuses a
    second, a fighter not in the fight, and any after the log holds a row
    other than `SessionStarted` and `RulingsStated` (the first opening
    split or Phase row closes the window). A power ruling must name a power on his build
    (checked here, where the build is whole; a replay from snapshots has
    only the recorded views).
    """
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import RulingsStated, make_author_engine

    combatant = session.combatants.get(combatant_id)
    if combatant is not None:
        owned = _by_id(combatant)
        unknown = sorted({r.power_id for r in rulings
                          if r.power_id is not None and r.power_id not in owned})
        if unknown:
            raise ValueError(
                f"rulings for {combatant_id!r} name powers his build does not "
                f"have: {unknown}")
    return apply_event(session, RulingsStated(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(UTC), author=make_author_engine(),
        combatant_id=combatant_id, rulings=tuple(rulings),
    ))


def rulings_for(session: CombatSession, combatant_id: str) -> tuple[Ruling, ...]:
    """His rulings, from the log. ``()`` when none were stated: nothing
    ruled."""
    for event in session.event_log:
        if (getattr(event, "kind", None) == "RulingsStated"
                and event.combatant_id == combatant_id):
            return tuple(event.rulings)
    return ()


def _self_contained_breathing(combatant: Any) -> bool:
    """Does his build in play close breath (6E1 p.247)? A fighter with no
    build (a stat block, an object) has none to read."""
    ask = getattr(combatant, "has_self_contained_breathing", None)
    return callable(ask) and ask()


def _closed_why(session: CombatSession, combatant_id: str
                ) -> dict[DeliveryRoute, list[str]]:
    """Each closed route on him, with what closed it, in the page's words."""
    why: dict[DeliveryRoute, list[str]] = {}
    for r in rulings_for(session, combatant_id):
        if r.power_id is None and BodyFact(r.fact) in CLOSES:
            why.setdefault(CLOSES[BodyFact(r.fact)], []).append(
                f'GM ruling: "{r.sentence}"')
    if _self_contained_breathing(session.combatants[combatant_id]):
        why.setdefault(DeliveryRoute.BREATH, []).append(SELF_CONTAINED_BREATHING)
    return why


def closed_routes(session: CombatSession, combatant_id: str
                  ) -> frozenset[DeliveryRoute]:
    """The routes nothing can reach him by: his body facts, and
    Self-Contained Breathing in the build he is in."""
    return frozenset(_closed_why(session, combatant_id))


def _source(actor: Any, action: LegalAction) -> Any:
    view = getattr(action, "_attack_view", None)
    if view is None:
        return None
    from kirby_combat.enumeration import source_power_of

    return source_power_of(actor, view)


def _power_routes(session: CombatSession, actor_id: str
                  ) -> dict[str, frozenset[DeliveryRoute]]:
    """His power rulings: HD ID -> the routes that power travels by."""
    by_power: dict[str, set[DeliveryRoute]] = {}
    for r in rulings_for(session, actor_id):
        if r.power_id is not None:
            by_power.setdefault(r.power_id, set()).add(DeliveryRoute(r.fact))
    return {pid: frozenset(routes) for pid, routes in by_power.items()}


def _by_id(actor: Any) -> dict[str, Any]:
    """Every purchase on his build as bought, by HD ID."""
    from kirby_combat.identity import _purchases

    return {str(p.id): p for p in _purchases(getattr(actor, "hero", None))
            if getattr(p, "id", None)}


def _routes(actor: Any, action: LegalAction,
            by_power: Mapping[str, frozenset[DeliveryRoute]],
            by_id: Mapping[str, Any]) -> frozenset[DeliveryRoute]:
    """Walk up from the offer's source power (its id, then each
    ``parent_id``) to the nearest purchase with a route ruling."""
    here = _source(actor, action)
    seen: set[str] = set()
    while here is not None and str(here.id) not in seen:
        pid = str(here.id)
        if pid in by_power:
            return by_power[pid]
        seen.add(pid)
        parent = getattr(here, "parent_id", None)
        here = by_id.get(str(parent)) if parent else None
    return frozenset()


def routes_of(session: CombatSession, actor_id: str,
              action: LegalAction) -> frozenset[DeliveryRoute]:
    """The routes the offer's power travels by: the nearest of its source
    power and that power's frameworks with a route ruling. Empty when none
    has one (most attacks), or the offer has no source power."""
    by_power = _power_routes(session, actor_id)
    if not by_power:
        return frozenset()
    actor = session.combatants[actor_id]
    return _routes(actor, action, by_power, _by_id(actor))


def _words(routes) -> str:
    ordered = [r.value for r in DeliveryRoute if r in routes]
    return (ordered[0] if len(ordered) == 1
            else f"{', '.join(ordered[:-1])} or {ordered[-1]}")


def rulings_gate(session: CombatSession, actor_id: str,
                 menu: list[LegalAction]
                 ) -> tuple[list[LegalAction], list[Withheld]]:
    """Take off the menu every offer whose routes are all closed on its
    target, and say why for each."""
    by_power = _power_routes(session, actor_id)
    if not by_power:
        return list(menu), []
    actor = session.combatants[actor_id]
    by_id = _by_id(actor)
    closed: dict[str, dict[DeliveryRoute, list[str]]] = {}
    kept: list[LegalAction] = []
    withheld: list[Withheld] = []
    for a in menu:
        target = a.target_id
        routes = (_routes(actor, a, by_power, by_id)
                  if target is not None and target in session.combatants
                  else frozenset())
        if routes and target not in closed:
            closed[target] = _closed_why(session, target)
        why = closed[target] if routes else {}
        if not routes or not routes <= set(why):
            kept.append(a)
            continue
        reasons: list[str] = []
        for route in DeliveryRoute:
            if route in routes:
                reasons.extend(w for w in why[route] if w not in reasons)
        name = session.combatants[target].name
        power = _source(actor, a).name or a.power_name
        withheld.append(Withheld(
            action_id=a.action_id, summary=a.summary,
            reason=(f"Not offered against {name}: {power} needs "
                    f"{_words(routes)}; {name} has none of them "
                    f"({'; '.join(reasons)})")))
    return kept, withheld


def ruling_lines(session: CombatSession) -> list[str]:
    """Every ruling in the fight, as the page shows it: whose, and the GM's
    sentence verbatim. One line per sentence a subject carries."""
    out: list[str] = []
    for cid, combatant in session.combatants.items():
        rulings = rulings_for(session, cid)
        if not rulings:
            continue
        owned = _by_id(combatant)
        for r in rulings:
            power = owned.get(r.power_id) if r.power_id is not None else None
            # A power ruling names a power he owns (`state_rulings`); a
            # fighter rebuilt from a snapshot has no build to name it from,
            # so the page names it by its HD ID.
            label = ((getattr(power, "name", "") or getattr(power, "alias", ""))
                     if power is not None else r.power_id)
            subject = (combatant.name if r.power_id is None
                       else f"{combatant.name}, {label}")
            line = f'{subject}: GM ruling: "{r.sentence}"'
            if line not in out:
                out.append(line)
    return out


__all__ = [
    "CLOSES",
    "SELF_CONTAINED_BREATHING",
    "BodyFact",
    "DeliveryRoute",
    "Ruling",
    "Withheld",
    "closed_routes",
    "routes_of",
    "ruling_lines",
    "rulings_for",
    "rulings_gate",
    "state_rulings",
]
