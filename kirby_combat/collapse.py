"""When a structure comes down on somebody.

PeterB, after a thrown wagon flattened Fly's Studio and hurt nobody:
"add the damage when the house collapses on ike".

THE DICE ARE THE BOOK'S. 6E2 p.142: "A character who falls 20m or less
takes 1d6 damage per full 2m fallen", physical Normal Damage. A building
landing on a man is that same fall with the roles swapped --- the mass
comes down the structure's height --- so Fly's Studio at 5m is 2d6 and the
Harwood House at 6m is 3d6.

WHO IT LANDS ON IS OURS. The book covers a character falling, not a
building landing, and says nothing about the footprint of a collapse. A
JUDGEMENT: anyone within two metres of the wall's line when it comes
down, which is roughly the ground a falling structure occupies. Stated as
a number so it can be argued with.

Damage goes through the ordinary attack pipeline, so defenses apply. A
brick standing in the rubble of a shack he has just knocked over shrugs
it off, and should.
"""
from __future__ import annotations

from typing import Any

#: 6E2 p.142. One die per FULL 2m --- a five-metre building is two dice,
#: not two and a half.
METRES_PER_DIE = 2.0

#: How far from the line of the wall the rubble reaches. A JUDGEMENT; the
#: book has no opinion about the footprint of a collapse.
COLLAPSE_RADIUS_M = 2.0


def collapse_damage_dice(height_m: float) -> int:
    """Dice of Normal Damage a structure of this height does as it falls."""
    return int(max(0.0, float(height_m or 0.0)) // METRES_PER_DIE)


def _distance_to_segment(point, a, b) -> float:
    """Metres from a point to a wall's line, in the plane."""
    px, py = point.x, point.y
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    if span <= 1e-9:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / span))
    nx, ny = ax + t * dx, ay + t * dy
    return ((px - nx) ** 2 + (py - ny) ** 2) ** 0.5


def caught_under(session: Any, construct: Any) -> list[str]:
    """Ids of everyone standing where this structure is about to land.

    TWO QUESTIONS, BOTH TRUE, and until interiors existed this could only
    ask the second.

    INSIDE. A man sheltering in the middle of Fly's Studio is under the
    roof, however far he is from any wall of it. `constructs_containing`
    has always been able to answer that --- polygon plus elevation range,
    the same machinery hazard zones use --- and no BUILDING was ever a
    volume for it to answer about.

    BESIDE. A man leaning on the outside is caught by the edge of the
    collapse. That is what this did, and it stays.

    A construct with no footprint --- every scene authored before
    interiors --- has no inside, so proximity answers alone and nothing
    that worked before changes.
    """
    scene = getattr(session, "scene", None)
    if scene is None:
        return []
    positions = (getattr(scene, "combatant_positions", None) or {})

    out: list[str] = []
    segment = getattr(construct, "segment", None)
    for cid, pos in positions.items():
        if _inside(pos, construct):
            out.append(cid)
        elif segment is not None:
            a, b = segment
            if _distance_to_segment(pos, a, b) <= COLLAPSE_RADIUS_M:
                out.append(cid)
    return out


def _inside(pos: Any, construct: Any) -> bool:
    """Is this position within the structure's footprint?

    Delegated to `constructs_containing` rather than re-deriving the
    point-in-polygon test: there must be ONE answer to "is he in there",
    and hazard zones have been asking it correctly for a long time.
    """
    if getattr(construct, "polygon_xy", None) is None:
        return False
    from kirby_combat.scene.construct import constructs_containing

    return bool(constructs_containing(pos, [construct]))


def bring_it_down(session: Any, construct: Any, *, roller, template):
    """Drop a destroyed structure on whoever is standing under it.

    Returns ``(session, [{"combatant_id", "stun", "body"}, ...])`` --- the
    caller records it, because a collapse is part of the action that
    caused it and not an event of its own.

    NO ROLL TO HIT. A building does not miss. Defenses still apply, which
    is the half that matters: a brick standing in the rubble of a shack he
    has just knocked over shrugs it off.
    """
    from kirby_combat.actions.recording import _apply_damage
    from kirby_combat.models import AttackPower, DiceValues
    from kirby_combat.resolution.damage import compute_damage

    dice = collapse_damage_dice(getattr(construct, "height_m", 0.0))
    if dice <= 0:
        return session, []

    rubble = AttackPower(
        xmlid="COLLAPSE", name="falling structure", damage_dice=dice,
        half_die=False, plus_one=False, damage_type="normal",
        defense_type="pd", range_m=0.0, uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id=f"collapse:{getattr(construct, 'obj_id', '?')}",
    )
    caught = []
    for cid in caught_under(session, construct):
        victim = session.combatants.get(cid)
        if victim is None:
            continue
        dmg = compute_damage(rubble, DiceValues(damage=roller.roll_dice(dice)),
                             template)
        stats = victim.combat_stats()
        # Normal Damage against ordinary PD. Resistant defenses count too ---
        # they are defenses, and 6E2 p.105 has them stopping Normal Damage
        # as well as Killing.
        defense = int(getattr(stats, "pd", 0) or 0)
        stun = max(0, int(dmg.stun) - defense)
        body = max(0, int(dmg.body) - defense)
        if stun or body:
            session = _apply_damage(session, cid, stun=stun, body=body)
        caught.append({"combatant_id": cid, "stun": stun, "body": body})

    # AND IT STOPS BEING IN THE WAY. `constructs_in` drops rubble from the
    # things you can hit, but `cover.py`, `perception.py` and
    # `movement_legality.py` all read `scene.walls` directly and nothing
    # hydrates that --- so a flattened house went on granting cover,
    # blocking line of sight and turning men's movement back. It came down
    # on three men in the O.K. Corral and they were still hiding behind
    # it.
    #
    # Taking it off the board is part of bringing it down, which is why
    # this lives here rather than in either caller.
    return _off_the_board(session, construct), caught


def _off_the_board(session: Any, construct: Any):
    """Remove a collapsed structure from the scene it was part of."""
    from dataclasses import replace

    scene = getattr(session, "scene", None)
    obj_id = getattr(construct, "obj_id", None)
    if scene is None or obj_id is None:
        return session
    walls = [w for w in (getattr(scene, "walls", None) or []) if w.id != obj_id]
    constructs = [c for c in (getattr(scene, "constructs", None) or [])
                  if getattr(c, "obj_id", None) != obj_id]
    if (len(walls) == len(getattr(scene, "walls", None) or [])
            and len(constructs) == len(getattr(scene, "constructs", None) or [])):
        return session
    return replace(session, scene=replace(scene, walls=walls,
                                          constructs=constructs))
