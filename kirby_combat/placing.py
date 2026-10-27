"""Where a caster puts a thing he aims at a place: a Barrier, a Darkness
field, an Image.

ONE ANSWER FOR THE MENU AND THE RESOLVER. `loop/resolvers.py` placed all three
"near the nearest enemy" and refused (`UnresolvableAction`) when the map could
not say where that was --- the caster or every enemy missing from
`Scene.combatant_positions`. Enumeration offered them on `has_scene` alone, so
the menu promised a wall the resolver could not raise: under
`run_phase(on_unresolvable="raise")` that is a stopped fight, and on kirby-api
a /run 500. The offer now asks the same question the resolver does, here.

Pure: positions in, a point out. No session, so enumeration (which holds none)
can ask it too.
"""
from __future__ import annotations

from typing import Any, Iterable


def point_short_of_nearest(
    here: Any, enemies: Iterable[tuple[str, Any]], standoff_m: float,
) -> tuple[float, float, float] | None:
    """A point ``standoff_m`` short of the nearest enemy, on the line back
    toward ``here``.

    ``enemies`` is ``(id, position)`` pairs; an enemy with no position is
    skipped. Ties on distance go to the lower id, so a seeded fight places
    the same way every run. Nose to nose (closer than ``standoff_m``) the
    point is the enemy's own spot rather than behind the caster, which is
    what a negative step would give.

    None when there is nowhere to put it: no ``here``, or no enemy on the map.
    """
    from kirby_world.geometry import distance_3d

    if here is None:
        return None
    placed = [(distance_3d(here, pos), eid, pos)
              for eid, pos in enemies if pos is not None]
    if not placed:
        return None
    gap, _, there = min(placed, key=lambda row: (row[0], row[1]))
    if gap <= standoff_m:
        return (there.x, there.y, there.z)
    t = (gap - standoff_m) / gap
    return (
        here.x + (there.x - here.x) * t,
        here.y + (there.y - here.y) * t,
        here.z + (there.z - here.z) * t,
    )


def has_a_place_near_an_enemy(scene: Any, actor_id: str, enemy_ids: Iterable[str]) -> bool:
    """Can `point_short_of_nearest` answer for this caster on this map?

    The standoff only moves the point, never whether there is one, so the
    menu asks without it.
    """
    positions = getattr(scene, "combatant_positions", None) or {}
    if positions.get(actor_id) is None:
        return False
    return any(positions.get(e) is not None for e in enemy_ids)
