"""Committing a move — the step that writes a landing back to the Scene.

THE GAP THIS CLOSES. The engine could decide a move completely and then
forget it. `scene/movement_legality.py::movement_reach` is a full pure
resolver: it takes a mode, a start, a destination and a movement capacity,
and returns where the mover actually ends up, clamped by walls, supporting
surfaces and reach, with any resulting fall. `MovementAction.resolve`
charges the END and emits a `MovementResolved`.

And nothing wrote the position down. Measured 2026-09-06:

* `MovementResolved` carries `from_pos` and `to_pos` fields, and
  `MovementAction.resolve` constructs one with **both hardcoded to None**.
* `scene.combatant_positions` is read all over the engine --- enumeration's
  range gate, line of sight, cover, Images placement --- and written
  NOWHERE outside a test fixture.

So a fight on a map was frozen: every combatant enumerated, attacked and
was attacked from the position they started in, forever. Nothing raised,
because a stationary fight is a perfectly valid fight.

WHY THIS IS ITS OWN MODULE. Deciding where someone can go is a rule and
lives in `movement_legality`. Recording that they went there is a rule too
--- the ledger of a fight includes where people are standing --- but it is a
different one, and putting it inside `movement_reach` would make a pure
"could I get there?" query mutate the world as a side effect.

AND IT NO LONGER WRITES (0.18.5). This module used to update
`scene.combatant_positions` in place and then emit a `MovementResolved`
that `apply_event` did nothing with --- mutate-then-log, the exact shape
Task A7 removed from the vitals. The consequence was the same: a session
rebuilt from its rows put every fighter at his starting placement for
ever, measured on a recorded fight as all fourteen checkpoints reporting
Wyatt at (3.1, 3.7) although he moved at sequence 7.

So `commit_move` now emits the row and the FOLD writes the Scene
(`session/apply.py::_fold_position`). One writer, and the live path and
the replayed path go through it in that same one place.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kirby_combat.scene.movement_legality import MovementOutcome, movement_reach
from kirby_combat.scene.scene import Position

if TYPE_CHECKING:
    from kirby_combat.scene.scene import Scene
    from kirby_combat.session.combat_session import CombatSession


def position_of(scene: "Scene | None", combatant_id: str) -> Position | None:
    """Where a combatant is standing, or ``None`` if they are not on the map.

    Not on the map is not the same as at the origin --- a combatant with no
    position is absent from every distance calculation rather than adjacent
    to whoever happens to be at (0, 0, 0).
    """
    if scene is None:
        return None
    return (getattr(scene, "combatant_positions", None) or {}).get(combatant_id)


def commit_move(
    session: "CombatSession",
    combatant_id: str,
    outcome: MovementOutcome,
) -> "CombatSession":
    """Write an already-decided landing onto the Scene.

    Takes a ``MovementOutcome`` rather than a destination, so the decision
    and the recording stay separate: this function never judges whether a
    move was legal, and `movement_reach` never moves anybody.

    An unreachable outcome still lands the mover at ``outcome.landing`` ---
    which `movement_reach` sets to the furthest point actually reached (or
    to the start, for a refusal). A partial move is a real move.

    WRITES NOTHING ITSELF. It records the move; `apply_event` applies it.
    See this module's docstring for the defect that split them.
    """
    scene = session.scene
    if scene is None:
        return session
    positions = getattr(scene, "combatant_positions", None)
    if positions is None:
        return session
    return _record_move(session, combatant_id, positions.get(combatant_id),
                        outcome)


def _record_move(session, combatant_id, start, outcome):
    """Put the move in the log, so a replay can draw it.

    `MovementResolved` is defined, exported, in the event union, handled by
    `apply_event` and round-trip tested --- and the LOOP had never emitted
    one. Two paths move people and only the other logged:
    `MovementAction.resolve` builds the event, while every loop resolver
    (`move_to_cover`, `disengage`, each `reposition`) came through here and
    said nothing.

    Measured on a recording of the O.K. Corral made for the Krackle
    replay: 22 actions, 8 of them movement, and ZERO MovementResolved.
    Watching it back, nobody moved --- the renderer had no way to know they
    had. `MovementAction.resolve`'s own comment already points here: "A
    caller that has a destination goes through `scene/placement.py`, which
    decides the landing and writes it onto the Scene."

    A ZERO-LENGTH MOVE IS NOT A MOVE. `movement_reach` lands a refusal back
    at the start, and a log full of those is noise a replay would animate
    as a twitch. FACING COUNTS as part of that comparison: a man who
    turns on the spot has moved, as far as anything drawing him is
    concerned.
    """
    import uuid
    from datetime import datetime, timezone

    landing = outcome.landing
    if start is not None and (start.x, start.y, start.z, start.facing) == (
            landing.x, landing.y, landing.z, landing.facing):
        return session

    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import (
        MovementResolved, make_author_combatant,
    )

    return apply_event(session, MovementResolved(
        id=str(uuid.uuid4()),
        session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(combatant_id),
        combatant_id=combatant_id,
        from_pos=({"x": start.x, "y": start.y, "z": start.z,
                   "facing": start.facing}
                  if start is not None else None),
        to_pos={"x": landing.x, "y": landing.y, "z": landing.z,
                "facing": landing.facing},
        velocity_mps=float(getattr(outcome, "distance_m", 0.0) or 0.0),
        move_type=getattr(outcome, "mode", None) or "move",
    ))


def move_toward(
    session: "CombatSession",
    combatant_id: str,
    destination: Position,
    *,
    mode: str,
    distance_m: float,
) -> tuple["CombatSession", MovementOutcome | None]:
    """Decide a move and commit it, in that order.

    The convenience the loop's resolvers want: ask `movement_reach` where
    the mover ends up, then write it down. Returns ``(session, None)`` when
    the question cannot be asked at all --- no Scene, or the mover is not on
    it --- rather than inventing a start point.
    """
    scene = session.scene
    start = position_of(scene, combatant_id)
    if scene is None or start is None:
        return session, None

    outcome = movement_reach(
        mode=mode, from_pos=start, to_pos=destination,
        distance_m=distance_m, scene=scene,
        combatant_id=combatant_id, session=session,
    )
    return commit_move(session, combatant_id, outcome), outcome


def blocked_by_furnishing(scene, pos):
    """The Furnishing standing on that spot, or None.

    THE QUESTION A LINE COULD NEVER ANSWER. Scenery was a `Wall` --- a
    segment with no width --- so it occupied no ground and nothing could
    refuse a man who walked into it. Measured on the O.K. Corral board,
    where the wagon is a 2 m line: Wyatt stands 0.40 m from it, Virgil
    0.50, Morgan 0.82, all three inside any wagon of a realistic size.

    ABOVE IT IS NOT INSIDE IT. A man on a wagon's bed is standing ON the
    thing, which is the same distinction `Scene.supporting_surfaces`
    already draws for wall tops --- and a furnishing you can walk through
    blocks nobody at any height.
    """
    for f in (getattr(scene, "furnishings", None) or []):
        if not f.blocks_movement:
            continue
        if getattr(pos, "z", 0.0) >= f.height_m:
            continue
        if f.occupies(pos.x, pos.y):
            return f
    return None
