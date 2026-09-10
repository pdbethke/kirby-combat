#!/usr/bin/env python3
"""Bake a fight into the JSON Krackle replays.

WHY A SCRIPT AND NOT AN ENGINE MODULE. kirby-combat is a Tier 1 pure
engine and this is a file format belonging to a front end, so it lives
out here beside `telemetry.py` for the same reason that one does. The
engine's contribution is `session.event_log` and
`kirby_combat.serialization.to_dict`, both of which already exist.

THE SHAPE, read off `kirby-app/src/lib/krackle/demoRecording.json`, which
kirby-api used to emit over a WebSocket before it was parked:

    {"snapshot": {session_id, scene_id, status, current_turn,
                  current_segment, last_sequence, scene, combatants,
                  constructs},
     "events":   [{sequence, event_type, author_id, payload}, ...]}

THE SNAPSHOT IS THE OPENING STATE, not the end. The existing demo page
ships an END snapshot and reverse-folds every event to reconstruct the
start, which the Krackle notes record as having "proved impossible" to do
faithfully -- END clamps at zero, and nothing ever emits RecoveryTaken or
StatusChanged, so those reversals are guesses. Recording the opening
directly removes the guess: a replay that starts from what actually
happened first cannot drift from it.

WHAT IT MAY RECORD. Only fights whose cast this repository is allowed to
publish. `the_ok_corral.py` loads archetypes and an arsenal out of the
Equipment Guide, and a recording of it carries their derived stat blocks
and weapon damage; `the_shootout_we_can_publish.py` was written so there
would be something to point this at. The check is not enforced here
because a script cannot know a licence -- it is stated so the next person
does.

    python scripts/record_for_krackle.py --out demoRecording.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "examples"))

from kirby_combat.serialization.to_dict import to_dict


def _flat(polygon) -> list[float]:
    """A polygon as the front end reads it.

    THE ENGINE SAYS PAIRS, KRACKLE SAYS FLAT. `Surface.polygon_xy` and
    `Construct.polygon_xy` are lists of (x, y) tuples; `polygon.ts` takes
    a flat [x1,y1,x2,y2,...] and pairs it itself. Emitting pairs is not a
    type error anywhere --- it is JSON either way --- so it fails SILENTLY
    and late: `polygonPoints` pairs the first two POINTS into one, comes
    back with two vertices, and `isDegenerate` skips the mesh rather than
    risk blanking the board.

    The cost of getting it wrong was every surface and every building
    vanishing. The lot rendered as two thin wall faces in a black void,
    which read as a corridor -- PeterB, twice: "doesnt much look like the
    tombstone layout", "still a cooridor". The geometry had been right the
    whole time and nothing was drawing it.
    """
    out: list[float] = []
    for point in polygon or []:
        out.extend(float(v) for v in point[:2])
    return out


def _scene_dict(scene) -> dict:
    """The scene as Krackle reads it.

    Walls arrive as `start` / `end` triples rather than the engine's
    `segment` pair of Positions, which is the one place the front end's
    shape and the engine's disagree.
    """
    def wall(w):
        a, b = w.segment
        return {
            "id": w.id, "name": w.name,
            "start": [a.x, a.y, a.z], "end": [b.x, b.y, b.z],
            "height_m": w.height_m, "blocks_los": w.blocks_los,
            "blocks_movement": w.blocks_movement,
            "cover_level": w.cover_level,
            "def_value": w.def_value, "body": w.body,
            # THE FACE'S BUILDING. Without it the front end cannot tell a
            # boarding-house wall from a stack of barrels, and draws the
            # face on top of the building mass behind it -- two coplanar
            # surfaces, which the renderer stripes. The filter that stops
            # that was written first and had nothing to read.
            "part_of": w.part_of,
        }

    def furnishing(f):
        return {
            "id": f.id, "name": f.name,
            "polygon_xy": _flat(f.polygon_xy),
            "height_m": f.height_m,
            "cover_level": f.cover_level,
            "blocks_los": f.blocks_los,
            "def_value": f.pd_value, "body": f.body_value,
            # The glTF a renderer may load instead of drawing primitives.
            # Never read by any rule; see `Furnishing.model`.
            "model": f.model,
        }

    def surface(s):
        return {
            "id": s.id, "name": s.name, "surface_type": s.surface_type,
            "elevation_m": s.elevation_m, "cover_level": s.cover_level,
            "is_supporting": True,
            "polygon_xy": _flat(s.polygon_xy),
        }

    b = scene.bounds
    return {
        "bounds": {"min_x": b.min_x, "min_y": b.min_y, "min_z": b.min_z,
                   "max_x": b.max_x, "max_y": b.max_y, "max_z": b.max_z},
        "ambient_light_level": getattr(scene.ambient, "light_level", 4),
        "walls": [wall(w) for w in (scene.walls or [])],
        "surfaces": [surface(s) for s in (scene.surfaces or [])],
        # SOLID THINGS, WITH THE GROUND THEY STAND ON. Their edges are
        # already in `walls` above -- the engine projects them so movement
        # and line of sight keep working -- and the front end needs the
        # FOOTPRINT to know how wide to draw a wagon, which a line could
        # never tell it. `part_of` on those edges is what stops it drawing
        # both.
        "furnishings": [furnishing(f) for f in (getattr(scene, "furnishings", None) or [])],
        "hazards": [],
    }


def _combatant_dict(c, scene) -> dict:
    """One fighter, as the SPD ribbon and status rail want him."""
    stats = c.combat_stats()
    state = c.state
    pos = (scene.combatant_positions or {}).get(c.id) if scene else None
    return {
        "character_id": c.id,
        "side": getattr(getattr(c, "side", None), "name", "") or "",
        "position": ({"x": pos.x, "y": pos.y, "z": pos.z,
                      "facing": getattr(pos, "facing", 0.0)}
                     if pos is not None else {"x": 0.0, "y": 0.0, "z": 0.0,
                                              "facing": 0.0}),
        "current_stun": state.current_stun,
        "current_body": state.current_body,
        "current_end": state.current_end,
        "is_prone": False, "is_stunned": False,
        "is_invisible": False, "is_hidden": False,
        "status_tokens": [],
        "name": getattr(c, "name", c.id),
        "spd": stats.spd, "dex": stats.dex,
        "max_stun": c.max_stun, "max_body": c.max_body, "max_end": c.max_end,
    }


def _construct_dict(k) -> dict:
    a, b = k.segment
    return {
        # `id`, not `obj_id`: the front end's constructs are keyed `id`,
        # which is what the reference recording emits.
        "id": k.obj_id, "obj_id": k.obj_id, "kind": k.kind,
        "start": [a.x, a.y, a.z], "end": [b.x, b.y, b.z],
        "height_m": k.height_m, "blocks_los": k.blocks_los,
        "blocks_movement": k.blocks_movement, "cover_level": k.cover_level,
        "def_value": k.def_value, "body": k.body,
        "polygon_xy": _flat(k.polygon_xy) or None,
    }


def _with_town(snapshot: dict) -> dict:
    """Add Tombstone around the lot, for the renderer only.

    SCENERY, NOT TERRAIN. Every `Construct` in a Scene becomes an
    `attack_construct` target, so putting ninety buildings in the Scene
    would flood every menu in the fight and let a man aim at a saloon four
    blocks away. The town is merged in HERE, after the fight is resolved,
    so the engine never sees it and the recording of the fight is
    unchanged.

    Nothing it adds blocks line of sight, gives cover or can be hit, and
    none of that matters for thirty seconds in a five-metre lot: the
    nearest thing it draws is across the street.
    """
    from tombstone_town import buildings, ground, streets

    scene = snapshot.get("scene")
    if scene is None:
        return snapshot
    # The streets go UNDER the fight's own ground, which is drawn last and
    # wins where they overlap.
    # ORDER IS THE WHOLE TRICK, since these all sit at elevation 0 and
    # coplanar surfaces z-fight: the desert first, the streets over it, and
    # the fight's own ground last so it wins where the men are standing.
    scene["surfaces"] = [
        {"id": s["id"], "name": s["name"], "surface_type": s["surface_type"],
         "elevation_m": 0.0, "cover_level": 0, "is_supporting": True,
         "polygon_xy": _flat(s["polygon"])}
        for s in [ground()] + streets()
    ] + scene["surfaces"]
    snapshot["constructs"] = list(snapshot.get("constructs") or []) + [
        {"id": b["id"], "obj_id": b["id"], "kind": "wall",
         "start": [b["polygon"][0][0], b["polygon"][0][1], 0.0],
         "end": [b["polygon"][2][0], b["polygon"][2][1], 0.0],
         "height_m": b["height"], "blocks_los": False,
         "blocks_movement": False, "cover_level": 0,
         "def_value": None, "body": None,
         "polygon_xy": _flat(b["polygon"])}
        for b in buildings()
    ]
    return snapshot


def opening_snapshot(session, scene) -> dict:
    """The fight as it stood before anybody acted."""
    return {
        "session_id": session.id,
        "scene_id": getattr(scene, "id", "") if scene else "",
        "status": "active",
        "current_turn": 1,
        "current_segment": session.timeline.segment,
        "last_sequence": 0,
        "scene": _scene_dict(scene) if scene else None,
        "combatants": [_combatant_dict(c, scene)
                       for c in session.combatants.values()],
        "constructs": [_construct_dict(k)
                       for k in (getattr(scene, "constructs", None) or [])],
    }


def events_of(session) -> list[dict]:
    """Every event, in the wrapper the front end unwraps."""
    out = []
    for i, event in enumerate(session.event_log, start=1):
        payload = to_dict(event)
        out.append({
            "sequence": getattr(event, "sequence", i),
            "event_type": getattr(event, "kind", ""),
            "author_id": getattr(getattr(event, "author", None), "id", "engine"),
            "payload": payload,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default="demoRecording.json")
    args = ap.parse_args()

    from the_shootout_we_can_publish import (
        DEMO_SEED, the_cast, the_fight, the_scene,
    )

    seed = DEMO_SEED if args.seed is None else args.seed

    # THE OPENING STATE IS REBUILT, not read off the finished session.
    # BOTH HALVES, and the first cut got this half wrong: the cast was
    # rebuilt at its starting vitals while the positions came off the
    # finished session's SCENE, whose `combatant_positions` the fight
    # mutates in place. So every man began the replay standing where he
    # ended it, the MovementResolved events moved him to where he already
    # was, and nobody appeared to move at all. `the_scene()` is a function
    # for exactly this reason.
    chooser, result = the_fight(seed)
    session = result.encounter.sessions[0]

    from dataclasses import replace as _replace

    fresh = {c.id: c for c in the_cast()}
    opening = _replace(session, combatants=fresh)
    snapshot = opening_snapshot(opening, the_scene())

    recording = {"snapshot": _with_town(snapshot),
                 "events": events_of(session)}
    path = pathlib.Path(args.out)
    path.write_text(json.dumps(recording, indent=1))
    print(f"wrote {path}  ({len(recording['events'])} events, "
          f"{len(snapshot['combatants'])} combatants, "
          f"{path.stat().st_size // 1024} KB)")
    print(f"  seed {seed}: {result.phases} Phases, "
          f"{'winner ' + result.winner.name if result.winner else 'undecided'}")


if __name__ == "__main__":
    main()
