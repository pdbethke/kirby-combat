"""Enraged and Berserk --- the rolls a Psychological fury makes in a fight.

6E1 p.424-425 (Complications chapter, ENRAGED/BERSERK), in our own words:

* The character names a CIRCUMSTANCE that sets him off, a chance to go
  (8-, 11- or 14-) and a chance to recover (14-, 11- or 8-).
* "Every Phase a character is in a situation where he can become Enraged,
  he should roll his chance"; at or under it, he is Enraged.
* Enraged, he mindlessly attacks whoever (or whatever) enraged him, with no
  defensive maneuvers (Dodge, Block, or actions primarily defensive),
  ignoring other targets and teammates who need help.
* Berserk (p.425, the optional stronger form, HD's BERSERK adder) cannot
  tell friend from foe: he attacks whoever is nearest until he Knocks them
  Out or kills them, then the nearest visible target.
* He rolls to recover when he finishes with his target, when he runs out of
  END, and --- free --- in Post-Segment 12 if he has not tried that Turn.
  Failing after finishing his target, an Enraged man turns on "the targets
  most closely related to his original target".

THE DRIVER THIS PORTS (the parked consumer's, `_maybe_enter_rage` /
`_maybe_recover_from_rage`, deleted in 70ad60f) got three things wrong, and
they are corrected here, not carried over:

1. It rolled to go whenever the man took BODY or a big hit, WHATEVER his
   circumstance said. A man Enraged "if insulted" went off when shot. The
   book's trigger is the character's own circumstance.
2. It rolled to recover every one of his Phases. The book names the
   occasions (above); every Phase is not one of them.
3. It defaulted a missing roll to 11-. Here a sheet that states no roll is
   a rage this engine does not run (see ``rage_complications_of``).

And it changed nothing mechanical --- the rage only suppressed the combat
AI's plan. Here it narrows the menu, which is the rule.

THE CIRCUMSTANCE IS FREE TEXT and this engine cannot judge most of it
("if insulted", "when betrayed", "if reminded of home"). RULING: it reads
three classes it CAN observe in the fight's own log, and only when a clause
of the text is exactly that class about the character himself:

* ``IN_COMBAT`` --- "in combat": always true in a fight.
* ``TAKES_BODY`` --- "if he takes BODY", "if wounded / injured / hurt",
  "when he sees his own blood": he lost BODY to an attack since his last
  Phase. The man who did it is the one who enraged him.
* ``ATTACKED`` --- "if attacked", "when hit": an enemy declared an action at
  him since his last Phase.

A circumstance about someone else ("if his sister is hurt"), about a special
effect ("if hit by electricity") or about anything social is the GM's call,
and the engine never rolls for it. ``classify`` is the whole of the reading
and is tested clause by clause.

Also built: the Concentration ban ("An Enraged (or Berserk) character cannot
use any powers that have the Complication Concentration", p.424; the menu
drops them, `RageMenu.narrowed`), and recovery when "someone attempts to snap
him out of it" (the `snap_out_of_rage` offer, `half_phase_offers.py`).

RULING, NO HOLDING. "When a character becomes Enraged, he mindlessly attacks
the individual (or object) that Enrages him" (p.424). Holding an Action is
waiting for a better moment, which is the one thing a mindless attack does
not do; `hold` is not offered while he rages.

NOT MODELLED, recorded rather than dropped: the CSL-to-DCV ban (nothing in the
loop allocates Combat Skill Levels to DCV), and the GM option against powers
with Extra Time longer than an Extra Segment.
"""
from __future__ import annotations

import enum
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


class Circumstance(enum.Enum):
    """The circumstance classes the engine can observe (see module doc)."""

    IN_COMBAT = "in_combat"
    TAKES_BODY = "takes_body"
    ATTACKED = "attacked"


class RollKind(enum.Enum):
    """Which of the complication's two rolls this is (6E1 p.425)."""

    GO = "go"
    RECOVER = "recover"


class RecoveryOccasion(enum.Enum):
    """When 6E1 p.424 gives him a roll to recover."""

    TARGET_DOWN = "target_down"            # "finishes with his target"
    OUT_OF_END = "out_of_end"              # "runs out of END"
    SNAPPED_OUT = "snapped_out"            # "when someone attempts to snap him out of it"
    POST_SEGMENT_12 = "post_segment_12"    # the free attempt each Turn


#: Each clause, normalised, that IS one of the classes. Anchored on purpose:
#: an unanchored "hurt" fires on "if his sister is seriously hurt".
_CLAUSES: tuple[tuple[re.Pattern, Circumstance], ...] = (
    (re.compile(r"^(?:if |when )?(?:he )?(?:is )?(?:in combat|in combat "
                r"situations)$"), Circumstance.IN_COMBAT),
    (re.compile(r"^(?:if |when )?(?:he )?(?:takes?|takeds) body"
                r"(?: damage)?(?: in combat| from an attack)?$"),
     Circumstance.TAKES_BODY),
    (re.compile(r"^(?:if |when )?(?:he )?(?:is )?(?:wounded|injured|hurt|"
                r"harmed)(?: in combat)?$"), Circumstance.TAKES_BODY),
    (re.compile(r"^(?:if |when )?(?:he )?sees his own blood$"),
     Circumstance.TAKES_BODY),
    (re.compile(r"^(?:if |when )?(?:he )?(?:is )?(?:attacked|hit)$"),
     Circumstance.ATTACKED),
)

_PARENTHETICAL = re.compile(r"\([^)]*\)")
_SPLIT = re.compile(r",|\bor\b|\band\b|/")


def classify(text: str) -> frozenset[Circumstance]:
    """The observable classes this circumstance text contains."""
    cleaned = _PARENTHETICAL.sub(" ", (text or "").lower())
    found: set[Circumstance] = set()
    for clause in _SPLIT.split(cleaned):
        clause = " ".join(clause.split())
        for pattern, circumstance in _CLAUSES:
            if pattern.match(clause):
                found.add(circumstance)
                break
    return frozenset(found)


@dataclass(frozen=True)
class RageComplication:
    """One ENRAGED complication, as the fight needs it."""

    complication_id: str
    circumstance_text: str
    circumstances: frozenset[Circumstance]
    berserk: bool
    go: int
    recover: int


_ROLL = re.compile(r"^\s*(\d+)\s*-?\s*$")


def _roll_of(adder) -> int | None:
    option = (getattr(adder, "option_id", None) or "")
    found = _ROLL.match(str(option))
    return int(found.group(1)) if found else None


def rage_complications_of(combatant: Any) -> list[RageComplication]:
    """Every Enraged/Berserk on this combatant's sheet that can run.

    HD writes Enraged as ``ENRAGED`` with CHANCETOGO / CHANCETORECOVER adders
    carrying the roll ("11-") and an optional BERSERK adder (6E1 p.425's +10
    form). Read off ``assigned_adders``, which is where kirby-cost keeps
    them. A complication missing either roll is NOT run: guessing one would
    be inventing the character (the parked driver guessed 11-). In the local
    corpus that is only the lossy random-fight copies.
    """
    hero = getattr(combatant, "hero", None)
    out: list[RageComplication] = []
    for raw in (getattr(hero, "complications", None) or []):
        if (getattr(raw, "xmlid", "") or "").upper() != "ENRAGED":
            continue
        adders = {
            (getattr(a, "xmlid", "") or "").upper(): a
            for a in (getattr(raw, "assigned_adders", None) or [])
        }
        go = _roll_of(adders.get("CHANCETOGO"))
        recover = _roll_of(adders.get("CHANCETORECOVER"))
        if go is None or recover is None:
            continue
        text = (getattr(raw, "input", "") or "").strip()
        out.append(RageComplication(
            complication_id=str(getattr(raw, "id", "") or ""),
            circumstance_text=text,
            circumstances=classify(text),
            berserk="BERSERK" in adders,
            go=go, recover=recover,
        ))
    # Berserk first: it is the stronger form (p.425), so a man carrying both
    # rolls for it first and an Enraged roll never masks it.
    return sorted(out, key=lambda c: not c.berserk)


@dataclass(frozen=True)
class RageState:
    """Folded from `RageRolled` / `RageTargeted`."""

    combatant_id: str
    raging: bool = False
    complication_id: str = ""
    berserk: bool = False
    target_id: str | None = None
    #: The Turn of his last recovery roll, for the free Post-Segment 12 one.
    last_recover_turn: int | None = None


def rage_state(session: "CombatSession", combatant_id: str) -> RageState:
    """Walk the log forward; nothing here is stored on a combatant."""
    raging = False
    complication_id = ""
    berserk = False
    target: str | None = None
    last_recover: int | None = None
    for evt in session.event_log:
        if getattr(evt, "combatant_id", None) != combatant_id:
            continue
        kind = getattr(evt, "kind", None)
        if kind == "RageRolled":
            if evt.roll_kind == RollKind.GO.value and evt.succeeded:
                raging = True
                complication_id = evt.complication_id
                berserk = evt.berserk
                target = evt.target_id or None
            elif evt.roll_kind == RollKind.RECOVER.value:
                last_recover = evt.turn
                if evt.succeeded:
                    raging, target = False, None
        elif kind == "RageTargeted" and raging:
            target = evt.target_id or None
    return RageState(
        combatant_id=combatant_id, raging=raging,
        complication_id=complication_id, berserk=berserk,
        target_id=target, last_recover_turn=last_recover,
    )


# ---------------------------------------------------------------------------
# Reading the fight
# ---------------------------------------------------------------------------

def _since_his_last_phase(session: "CombatSession", combatant_id: str) -> list:
    log = session.event_log
    for index in range(len(log) - 1, -1, -1):
        evt = log[index]
        if (getattr(evt, "kind", None) == "PhaseSpent"
                and getattr(evt, "combatant_id", None) == combatant_id):
            return log[index + 1:]
    return list(log)


def _is_enemy(session, a_id: str, b_id: str) -> bool:
    from kirby_combat.side import Side

    a, b = session.combatants.get(a_id), session.combatants.get(b_id)
    return a is not None and b is not None and Side.of(a) != Side.of(b)


def _provoker(session, combatant_id: str, circumstance: Circumstance) -> tuple[bool, str | None]:
    """(does it hold, who caused it) for an event-driven circumstance."""
    last_declarer: str | None = None
    found, who = False, None
    for evt in _since_his_last_phase(session, combatant_id):
        kind = getattr(evt, "kind", None)
        if kind == "ActionDeclared":
            last_declarer = getattr(evt, "combatant_id", None)
            if (circumstance is Circumstance.ATTACKED
                    and combatant_id in (getattr(evt, "targets", None) or [])
                    and last_declarer and last_declarer != combatant_id
                    and _is_enemy(session, combatant_id, last_declarer)):
                found, who = True, last_declarer
        elif (kind == "VitalsChanged" and circumstance is Circumstance.TAKES_BODY
              and getattr(evt, "combatant_id", None) == combatant_id
              and int(getattr(evt, "body", 0) or 0) < 0
              and getattr(evt, "reason", "") == "damage"):
            found = True
            if last_declarer and last_declarer != combatant_id:
                who = last_declarer
    return found, who


def _standing(session, combatant_id: str):
    from kirby_combat.enumeration import is_down
    from kirby_combat.roster import Roster

    c = session.combatants.get(combatant_id)
    return c is not None and not is_down(c) and Roster(session).on_the_board(combatant_id)


def _nearest(session, actor_id: str, candidates: Iterable) -> str | None:
    """The nearest candidate by the scene's positions; with no positions to
    measure, the first in the roster's order (a ruling: "nearest" cannot be
    read off a fight on no map)."""
    candidates = [c for c in candidates if c.id != actor_id and _standing(session, c.id)]
    if not candidates:
        return None
    scene = getattr(session, "scene", None)
    if scene is not None:
        from kirby_world.geometry import distance_3d
        from kirby_world.occupancy import position_of

        here = position_of(scene, actor_id)
        if here is not None:
            measured = [(distance_3d(here, there), i, c.id)
                        for i, c in enumerate(candidates)
                        if (there := position_of(scene, c.id)) is not None]
            if measured:
                return min(measured)[2]
    return candidates[0].id


def _first_target(session, actor, rage: RageComplication, provoker: str | None) -> str | None:
    from kirby_combat.roster import Roster

    if rage.berserk:
        # p.425: "whoever's in front of them or nearest to them", friend or foe.
        return _nearest(session, actor.id, session.combatants.values())
    if provoker is not None and _standing(session, provoker):
        return provoker
    # RULING: a fury set off by the fight itself ("in combat") fixes on the
    # nearest enemy --- the fight enraged him, and p.424 has him attack one
    # target until he finishes with it.
    return _nearest(session, actor.id, Roster(session).enemies_of(actor))


def _next_target(session, actor, state: RageState) -> str | None:
    from kirby_combat.roster import Roster
    from kirby_combat.side import Side

    if state.berserk:
        return _nearest(session, actor.id, session.combatants.values())
    # p.424: "starting with the targets most closely related to his original
    # target". RULING: his side first, nearest first; then any enemy.
    old = session.combatants.get(state.target_id or "")
    if old is not None:
        kin = [c for c in session.combatants.values()
               if c.id != actor.id and Side.of(c) == Side.of(old)]
        picked = _nearest(session, actor.id, kin)
        if picked is not None:
            return picked
    return _nearest(session, actor.id, Roster(session).enemies_of(actor))


# ---------------------------------------------------------------------------
# Writing it down
# ---------------------------------------------------------------------------

def _rolled(session, actor_id, rage_id, roll_kind: RollKind, roll, number,
            *, berserk, target_id, reason) -> "CombatSession":
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import RageRolled, make_author_engine

    return apply_event(session, RageRolled(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id=actor_id, complication_id=rage_id,
        roll_kind=roll_kind.value, roll=roll, target_number=number,
        succeeded=roll <= number, berserk=berserk,
        target_id=target_id or "", reason=reason,
        turn=int(session.timeline.turn), segment=int(session.timeline.segment),
    ))


def _retargeted(session, actor_id, target_id, reason) -> "CombatSession":
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import RageTargeted, make_author_engine

    return apply_event(session, RageTargeted(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id=actor_id, target_id=target_id or "", reason=reason,
    ))


def _complication(combatant, complication_id: str) -> RageComplication:
    for rage in rage_complications_of(combatant):
        if rage.complication_id == complication_id:
            return rage
    raise ValueError(
        f"{combatant.id} is raging under complication {complication_id!r}, "
        f"which his sheet does not carry"
    )


def _try_to_recover(session, actor, state: RageState, occasion: RecoveryOccasion, roller):
    rage = _complication(actor, state.complication_id)
    return _rolled(
        session, actor.id, rage.complication_id, RollKind.RECOVER,
        sum(roller.roll_dice(3)), rage.recover,
        berserk=state.berserk, target_id=state.target_id, reason=occasion.value,
    )


def try_to_recover(session: "CombatSession", combatant_id: str,
                   occasion: RecoveryOccasion, roller) -> "CombatSession":
    """His recovery roll on ``occasion``. Raises if he is not raging: an
    occasion to calm down needs a fury to calm."""
    state = rage_state(session, combatant_id)
    if not state.raging:
        raise ValueError(f"{combatant_id!r} is not raging; there is nothing to recover from")
    return _try_to_recover(session, session.combatants[combatant_id], state,
                           occasion, roller)


def rage_phase_start(session: "CombatSession", actor_id: str, roller) -> "CombatSession":
    """The rolls a rage owes at the top of his Phase (6E1 p.424-425)."""
    actor = session.combatants[actor_id]
    state = rage_state(session, actor_id)
    if state.raging:
        occasion = None
        if state.target_id is None or not _standing(session, state.target_id):
            occasion = RecoveryOccasion.TARGET_DOWN
        elif int(getattr(actor, "current_end", 1) or 0) <= 0:
            occasion = RecoveryOccasion.OUT_OF_END
        if occasion is not None:
            session = _try_to_recover(session, actor, state, occasion, roller)
            state = rage_state(session, actor_id)
        if state.raging and (state.target_id is None
                             or not _standing(session, state.target_id)):
            target = _next_target(session, actor, state)
            if target is not None:
                session = _retargeted(session, actor_id, target, "target_down")
        return session

    for rage in rage_complications_of(actor):
        holds, provoker = False, None
        for circumstance in sorted(rage.circumstances, key=lambda c: c.value):
            if circumstance is Circumstance.IN_COMBAT:
                holds = True
            else:
                found, who = _provoker(session, actor_id, circumstance)
                if found:
                    holds, provoker = True, provoker or who
        if not holds:
            continue
        roll = sum(roller.roll_dice(3))
        target = _first_target(session, actor, rage, provoker) if roll <= rage.go else None
        reason = ",".join(sorted(c.value for c in rage.circumstances))
        session = _rolled(
            session, actor_id, rage.complication_id, RollKind.GO, roll, rage.go,
            berserk=rage.berserk, target_id=target, reason=reason,
        )
        if roll <= rage.go:
            break
    return session


def rage_post_segment_12(session: "CombatSession", roller) -> "CombatSession":
    """The free recovery attempt for anyone raging who has not tried this Turn."""
    for combatant_id in list(session.combatants):
        state = rage_state(session, combatant_id)
        if not state.raging or state.last_recover_turn == session.timeline.turn:
            continue
        if not _standing(session, combatant_id):
            continue
        session = _try_to_recover(
            session, session.combatants[combatant_id], state,
            RecoveryOccasion.POST_SEGMENT_12, roller,
        )
    return session


#: What a raging man may not do: "defensive maneuvers, such as Dodge or
#: Block, or ... actions the GM considers primarily defensive" (6E1 p.424;
#: p.425 for Berserk). RULING: hiding, breaking contact and running for
#: cover are primarily defensive.
DEFENSIVE_KINDS = frozenset({
    "dodge", "block", "hide", "disengage", "move_to_cover", "reposition",
})


#: What a mindless attacker does not do: wait (see the module's ruling).
WAITING_KINDS = frozenset({"hold"})


@dataclass(frozen=True)
class RageMenu:
    """How a rage reshapes who he fights and what he may do."""

    enemies: list
    allies: list
    may_abort: bool

    @staticmethod
    def without_defence(menu: Iterable) -> list:
        return [a for a in menu if a.kind not in DEFENSIVE_KINDS]

    @staticmethod
    def narrowed(menu: Iterable) -> list:
        """What a raging man may do: no defence, no waiting (the ruling
        above), and no power bought with Concentration (p.424)."""
        from kirby_combat.concentration import without_concentration_powers

        return without_concentration_powers(
            a for a in RageMenu.without_defence(menu) if a.kind not in WAITING_KINDS)


def rage_menu(session: "CombatSession", actor, enemies: list, allies: list) -> RageMenu | None:
    """None when he is not raging; otherwise who he may fight.

    He fights ONLY his target (Berserk: even a friend) and helps nobody;
    with no target to lock on (nobody standing), his enemies are unchanged.
    No Abort: an Abort is to a defensive Action (6E2 p.23).
    """
    state = rage_state(session, actor.id)
    if not state.raging:
        return None
    target = session.combatants.get(state.target_id or "")
    if target is not None and _standing(session, target.id):
        enemies = [target]
    return RageMenu(enemies=enemies, allies=[], may_abort=False)
