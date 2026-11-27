"""A standing horse is cover: Behind Cover like a wagon, and it moves with him.

6E2 p.45: "If a character has some cover from an opponent, the GM should
decide what Hit Locations are covered." The record has Tom McLaury behind a
horse at the O.K. Corral. RULING (Peter, 2026-11-27): a standing neutral
body --- a horse --- shelters a man the way a furnishing its size does, from
shooters on its far side; when it bolts or falls the cover goes with it.

HOW. Each question about cover is asked of the scene with every such body
put in as a `Furnishing` at the body's position (`with_bodies`), the shooter
and the target left out. The real scene is never changed, so a horse blocks
no movement and nothing can walk into one.

THE FOOTPRINT. Read off the sheet's Large complication (`size`): 4m Large is
a horse, 2.4m nose to tail and 0.8m across, 1.6m high, cover 2 like the
wagon, laid along the street (east-west: x). A shot its cover blocks does
the man no damage and does not hurt the horse either (not modelled).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

LENGTH_M, WIDTH_M, HEIGHT_M = 2.4, 0.8, 1.6
COVER_LEVEL = 2


def sheltering_bodies(session: "CombatSession") -> list[Any]:
    """Every neutral body still on its feet and on the field, and Large."""
    from kirby_combat.enumeration import is_down
    from kirby_combat.nerve import nerve_state
    from kirby_combat.roster import Roster
    from kirby_combat.side import Side
    from kirby_combat.size import ocv_to_hit

    roster = Roster(session)
    return [c for c in session.combatants.values()
            if Side.of(c).neutral and not is_down(c)
            and not roster.has_left(c.id) and nerve_state(session, c.id) is None
            and ocv_to_hit(c) > 0]


def with_bodies(session: "CombatSession", *, excluding: tuple[str, ...]) -> Any:
    """The scene, with a cover furnishing at every sheltering body."""
    from dataclasses import replace

    from kirby_world.scene import Furnishing

    scene = session.scene
    if scene is None:
        return None
    positions = getattr(scene, "combatant_positions", None) or {}
    added = []
    for body in sheltering_bodies(session):
        if body.id in excluding or body.id not in positions:
            continue
        p = positions[body.id]
        dx, dy = LENGTH_M / 2, WIDTH_M / 2
        # ITS OWN DEFENCES, as the cover's: the horse is what the shot meets.
        stats = body.combat_stats()
        added.append(Furnishing(
            id=f"body:{body.id}", name=getattr(getattr(body, "hero", None), "name", body.id),
            polygon_xy=[(p.x - dx, p.y - dy), (p.x + dx, p.y - dy),
                        (p.x + dx, p.y + dy), (p.x - dx, p.y + dy)],
            height_m=HEIGHT_M, cover_level=COVER_LEVEL, blocks_movement=False,
            pd=int(stats.pd), ed=int(stats.ed), body=int(body.state.current_body)))
    if not added:
        return scene
    return replace(scene, furnishings=list(scene.furnishings) + added)
