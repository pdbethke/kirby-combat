"""Knocked off the board, and coming back.

PETER'S RULING (2026-10-29): the edge of the map is not the edge of the
world. Knockback, a Throw or a shove (6E2 p.116-118) can carry a man past
it; until this ruling `Roster.has_left` read that as "gone" and he was out
of the fight for good --- 4 of 6 demo seeds rang somebody out that way.
Now he is coming back, and the engine works out how:

- WHERE TO: the point where he crossed the edge (`exit_point`), along the
  line he flew. Nothing is authored beyond the edge, so that line is clear.
  He comes back there and nowhere else: a teleporter could choose any
  spot in range, but every choice the engine weighs is worked out from a
  position ON the board, so the engine takes none from off it.
- HOW FAST: COMBAT speed. 6E2 p.25-26: a Full Move is his combat
  movement, and a move of half of it or less is a Half Phase Action.
  Noncombat speed (6E2 p.26) was rejected: its 1/2 DCV and 0 OCV, and p.27's
  limit on accelerating, are state the engine does not carry.
- BY WHICH MODE: the one that gets him back in the FEWEST Phases, of
  running, leaping, flight and teleportation (`way_back`). A tie goes to
  the lower END per 10m, then to `_ORDER`. A man in the air can only fly or
  teleport; swimming and tunneling do not cross open ground.
- GETTING UP: a man on the ground spends a Half Phase getting up first
  (6E2 p.116: "must spend a Half Phase to get up"), so his first Phase
  covers half his movement. Breakfall's Zero Phase stand-up (6E1 p.68) has
  already been tried at the top of the Phase.
- WHILE HE IS OFF: nobody can target him and he has not left --- his side
  is not beaten while he is on his way back. The loop spends his Phases
  moving him (`come_back`); he is never handed a menu.
- ARRIVING: if the move that brings him back used half his movement or
  less, a Half Phase is still his, and the next step hands him the menu
  from the edge (6E2 p.26).
- NO WAY BACK at all (no mode he can use) is leaving. So is walking off:
  only a FORCED move puts a man off the board rather than out of the fight.

Read off positions and the log, never a flag, the same way `Roster` reads
leaving: the forced move that crossed the edge is the record.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession
    from kirby_world.scene import Position, SceneBounds

#: The `MovementResolved.move_type`s an attack forces on a man: Knockback
#: (`impact.apply_knockback`), a Throw (`resolvers`) and a shove
#: (`martial_resolution`). Any other move across the edge was his own.
FORCED_MOVES = frozenset({"knockback", "thrown", "shoved"})

#: The modes that bring a man back over open ground, and the order that
#: breaks a tie the END cost has not.
_ORDER = ("running", "leaping", "flight", "teleportation")
_IN_THE_AIR = frozenset({"flight", "teleportation"})

_EPS = 1e-6

#: How far inside the edge the ground is asked about: on the edge itself a
#: surface's polygon boundary may or may not count as inside.
_INSIDE_BY_M = 0.01


@dataclass(frozen=True)
class WayBack:
    """How he comes back: by ``mode``, at ``combat_m`` a Phase, in ``phases``."""

    mode: str
    combat_m: float
    end_per_10m: int
    distance_m: float
    phases: int


def phases_needed(combat_m: float, distance_m: float, *, prone: bool) -> int:
    """Phases to cover ``distance_m`` at combat speed, getting up first if
    ``prone`` (half of the first Phase, 6E2 p.116)."""
    first = combat_m / 2.0 if prone else combat_m
    if distance_m <= first + _EPS:
        return 1
    return 1 + math.ceil((distance_m - first) / combat_m - _EPS)


def way_back(capabilities, *, distance_m: float, prone: bool,
             airborne: bool) -> WayBack | None:
    """The mode that brings him back soonest, or None if none can.

    ``capabilities`` is his `movement_view()`. A mode listed twice (a VPP
    can surface two) counts at its best.
    """
    usable = _IN_THE_AIR if airborne else frozenset(_ORDER)
    best: dict[str, Any] = {}
    for cap in capabilities:
        if cap.mode not in usable or float(cap.combat_m or 0) <= 0:
            continue
        if cap.mode not in best or cap.combat_m > best[cap.mode].combat_m:
            best[cap.mode] = cap
    if not best:
        return None
    options = [
        WayBack(mode=cap.mode, combat_m=float(cap.combat_m),
                end_per_10m=int(cap.end_per_10m), distance_m=float(distance_m),
                phases=phases_needed(float(cap.combat_m), distance_m, prone=prone))
        for cap in best.values()
    ]
    return min(options, key=lambda w: (w.phases, w.end_per_10m, _ORDER.index(w.mode)))


# ---------------------------------------------------------------------------
# Where he is
# ---------------------------------------------------------------------------

def _inside(bounds: "SceneBounds", x: float, y: float) -> bool:
    return (bounds.min_x - _EPS <= x <= bounds.max_x + _EPS
            and bounds.min_y - _EPS <= y <= bounds.max_y + _EPS)


def _bounds(session: "CombatSession"):
    scene = getattr(session, "scene", None)
    return None if scene is None else getattr(scene, "bounds", None)


def outside_the_bounds(session: "CombatSession", combatant_id: str) -> bool:
    """Is he beyond the map's edge? No scene, no bounds or no position for
    him means the question does not arise (most fights have no map)."""
    bounds = _bounds(session)
    pos = (getattr(session.scene, "combatant_positions", None) or {}).get(
        combatant_id) if bounds is not None else None
    if pos is None:
        return False
    return not _inside(bounds, pos.x, pos.y)


def exit_point(bounds: "SceneBounds", start: dict, end: dict) -> tuple[float, float, float]:
    """Where the line from ``start`` (on the board) to ``end`` (off it)
    crosses the edge."""
    t = 1.0
    for axis, lo, hi in (("x", bounds.min_x, bounds.max_x),
                         ("y", bounds.min_y, bounds.max_y)):
        a, b = float(start[axis]), float(end[axis])
        if b > hi:
            t = min(t, (hi - a) / (b - a))
        elif b < lo:
            t = min(t, (lo - a) / (b - a))
    x = min(max(start["x"] + t * (end["x"] - start["x"]), bounds.min_x), bounds.max_x)
    y = min(max(start["y"] + t * (end["y"] - start["y"]), bounds.min_y), bounds.max_y)
    return (x, y, float(start["z"]))


def _crossing(session: "CombatSession", combatant_id: str):
    """The last move of his that took him from the board to beyond it."""
    bounds = _bounds(session)
    for evt in reversed(session.event_log):
        if (getattr(evt, "kind", None) != "MovementResolved"
                or evt.combatant_id != combatant_id or evt.to_pos is None):
            continue
        frm, to = evt.from_pos, evt.to_pos
        if (_inside(bounds, frm["x"], frm["y"])
                and not _inside(bounds, to["x"], to["y"])):
            return evt
    return None


def _forced_crossing(session: "CombatSession", combatant_id: str):
    """The forced move that put him off the board, if that is how he got
    there; None if he is on it, or walked off."""
    if not outside_the_bounds(session, combatant_id):
        return None
    row = _crossing(session, combatant_id)
    if row is None or row.move_type not in FORCED_MOVES:
        return None
    return row


def _plan(session: "CombatSession", combatant_id: str, row) -> tuple[WayBack | None, "Position"]:
    """His way back from where he is now to the edge, and the point on it."""
    from kirby_world.scene import Position

    from kirby_world.falling import is_supported_at

    from kirby_combat.standing import is_prone

    here = session.scene.combatant_positions[combatant_id]
    ex, ey, _ = exit_point(session.scene.bounds, row.from_pos, row.to_pos)
    target = Position(ex, ey, here.z, here.facing)
    distance = math.hypot(ex - here.x, ey - here.y)
    # In the air out here means in the air where he crossed: the ground
    # beyond the edge is the ground at the edge (see the module docstring),
    # and `impact.is_airborne` would find none and put every man aloft.
    dx, dy = row.to_pos["x"] - row.from_pos["x"], row.to_pos["y"] - row.from_pos["y"]
    mag = math.hypot(dx, dy) or 1.0
    at_the_edge = Position(ex - dx / mag * _INSIDE_BY_M, ey - dy / mag * _INSIDE_BY_M,
                           here.z, here.facing)
    back = way_back(
        session.combatants[combatant_id].movement_view(), distance_m=distance,
        prone=is_prone(session, combatant_id),
        airborne=not is_supported_at(at_the_edge, session.scene),
    )
    return back, target


def is_off_board(session: "CombatSession", combatant_id: str) -> bool:
    """Forced off the board and able to come back: not a target, not gone."""
    row = _forced_crossing(session, combatant_id)
    if row is None:
        return False
    back, _ = _plan(session, combatant_id, row)
    return back is not None


# ---------------------------------------------------------------------------
# Saying so, and coming back
# ---------------------------------------------------------------------------

def _due_back(session: "CombatSession", combatant_id: str, phases: int) -> tuple[int, int]:
    """The Turn and Segment of his ``phases``-th Phase from now, counting
    this Segment's if his slot in it is still unspent."""
    from kirby_combat.tables import segments_for_spd

    timeline = session.timeline
    mine = segments_for_spd(session.combatants[combatant_id].combat_stats().spd)
    turn, segment = int(timeline.turn), int(timeline.segment)
    if not mine:
        raise ValueError(f"{combatant_id!r} has no Phases at all (SPD 0)")
    unspent_now = any(slot.combatant_id == combatant_id and not slot.has_acted
                      for slot in timeline.acting_order)
    count = 1 if unspent_now else 0
    while count < phases:
        segment += 1
        if segment > 12:
            turn, segment = turn + 1, 1
        if segment in mine:
            count += 1
    return turn, segment


def announce(session: "CombatSession") -> "CombatSession":
    """Write `ForcedOffTheBoard` for anybody forced off since it was last
    written --- once per trip, at the end of the step that put him there."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ForcedOffTheBoard, make_author_engine

    for combatant_id in list(session.combatants):
        row = _forced_crossing(session, combatant_id)
        if row is None:
            continue
        at = session.event_log.index(row)
        if any(getattr(e, "kind", None) == "ForcedOffTheBoard"
               and e.combatant_id == combatant_id
               for e in session.event_log[at + 1:]):
            continue
        back, target = _plan(session, combatant_id, row)
        if back is None:
            continue        # no way back: he has left, and `Roster` says so
        turn, segment = _due_back(session, combatant_id, back.phases)
        session = apply_event(session, ForcedOffTheBoard(
            id=str(uuid.uuid4()), session_id=session.id,
            sequence=len(session.event_log) + 1,
            timestamp=datetime.now(timezone.utc), author=make_author_engine(),
            combatant_id=combatant_id, cause=row.move_type,
            exit_point={"x": target.x, "y": target.y, "z": target.z},
            distance_m=back.distance_m, mode=back.mode,
            metres_per_phase=back.combat_m, phases=back.phases,
            returns_turn=turn, returns_segment=segment,
        ))
    return session


def _half_used(session: "CombatSession", combatant_id: str, kind: str,
               action_id: str) -> "CombatSession":
    from kirby_combat.action_time import ActionTime
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import PhaseTimeUsed, make_author_engine

    return apply_event(session, PhaseTimeUsed(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id=combatant_id, action_kind=kind, action_id=action_id,
        time=ActionTime.HALF.value,
        turn=int(session.timeline.turn), segment=int(session.timeline.segment),
    ))


def come_back(session: "CombatSession", combatant_id: str) -> tuple["CombatSession", bool, str]:
    """Spend his Phase coming back. Returns ``(session, goes_on, note)``:
    ``goes_on`` is True when he is back with a Half Phase still his, and
    the caller must not spend the slot."""
    from kirby_combat.action_time import halves_left
    from kirby_combat.impact import _record_move
    from kirby_combat.standing import is_prone, stand_up

    row = _forced_crossing(session, combatant_id)
    back, target = _plan(session, combatant_id, row) if row is not None else (None, None)
    if back is None:
        raise ValueError(f"{combatant_id!r} is not off the board with a way back")

    if is_prone(session, combatant_id):
        session, _ = stand_up(session, combatant_id)
        session = _half_used(session, combatant_id, "stand_up", "stand_up")
    halves = halves_left(session, combatant_id)
    allowance = back.combat_m * halves / 2.0
    here = session.scene.combatant_positions[combatant_id]
    moved = min(back.distance_m, allowance)
    if back.distance_m <= allowance + _EPS:
        end = target
    else:
        f = moved / back.distance_m
        from kirby_world.scene import Position
        end = Position(here.x + f * (target.x - here.x),
                       here.y + f * (target.y - here.y), here.z, here.facing)
    session = _record_move(session, combatant_id, here, end,
                           move_type=back.mode, distance_m=moved)
    arrived = end is target
    used = 1 if moved <= back.combat_m / 2.0 + _EPS else 2
    if arrived and halves - used > 0:
        session = _half_used(session, combatant_id, "half_move",
                             f"return_to_board:{back.mode}")
        return session, True, (
            f"{combatant_id} is back on the board ({back.mode}, {moved:g}m, a "
            f"Half Move); the rest of his Phase is his (6E2 p.26)")
    if arrived:
        return session, False, (
            f"{combatant_id} is back on the board ({back.mode}, {moved:g}m)")
    return session, False, (
        f"{combatant_id} is off the board, coming back by {back.mode}: "
        f"{moved:g}m this Phase, {back.distance_m - moved:g}m to go")
