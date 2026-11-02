"""The threat picture: what each enemy he can perceive has SHOWN he can do.

For a fighter, one `ThreatLine` per perceived enemy power that has been seen
in use this fight, saying whether it reaches him now, which defences answer
it (`defences.answers_to`, the table the reaction menu is cut from), and, for
an area, how many of his own squad one use would catch. Beside the lines:
how many enemies can reach him, how many of his side each enemy can reach,
and the best three places to take cover. Every AI seat reads it: orders, the
page, the EV seat's pricing. Nothing here rolls or writes.

RULINGS
* SEEN, NOT OWNED. Only a power the enemy has used while he is perceived
  counts (`judgement.powers_seen`, with the same SEEN POWERS ruling as the
  judged page). A power on his sheet he has not used is no line: a man does
  not know what another man could do. The page's `MAX_SEEN` cap is not
  applied: a seat reads all of it.
* ONLY WHAT ACTS ON A MAN. A seen power whose kind does not threaten a man
  (`defences.threatens_a_man`: a move, a Hold ...) gets no line.
* KIND IS WHAT HE USED IT AS. The kind comes from the first row that records
  the use (`ActionResolved.kind`, else the declaration's `action_type`), not
  from the power's view: one power is offered under several kinds (a Blast
  as `attack`, `rapid_fire`, `autofire`), and the kind is what picks the
  defence row. The view, when his sheet has one by that name, supplies the
  range and the area. A side-effect row records nothing he chose to do to a
  man and is skipped.
* REACH, NOW. A hand-to-hand power reaches a man inside the enemy's melee
  reach (`actions.reach.within_reach`, 6E2 p.56); a No Range area reaches
  as far as its size (as enumeration's `_no_range_area_covers`); a ranged
  power must be inside its range and have line of sight
  (`resolution.line_of_sight.has_line_of_sight`, 6E1 p.339 for Indirect).
  RULING: a ranged power's range is a MAXIMUM, the metres `hero_view` sets
  from its Active Points (`AttackPower.range_m`; the loader cites no page
  for the cap itself). KNOWN ENGINE GAP, recorded for a later fix:
  `enumerate_actions` does not yet gate maximum range on ranged offers (only
  line of sight), so an enemy may be OFFERED a shot this picture says
  cannot reach. The picture follows the rule, not the gap.
  "Now" means from where each stands, not after a move. With no map,
  nobody can be shown out of reach, so it reaches.
* THE SQUAD AN AREA WOULD CATCH is counted from HIM: the standing men of his
  own side and squad, other than himself, within the area's size of where he
  stands. With no map nobody can be shown beside him, so it is 0 (the same
  ruling `area_attack` makes about who an area holds). None unless the line
  is an area and he is in a squad.
* COVER is `kirby_world.cover.cover_spots` against the perceived enemies'
  positions, best three. ``reach_m`` is how far a `move_to_cover` offer can take him: a Half
  Move in Running (`enumeration.cover_half_move`, the one the menu uses),
  so "reachable this Phase" and a `move_to_cover` offer agree. It is NOT
  the situation's ``reach_m``, which is his melee reach (6E2 p.56).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kirby_combat.actions.area_attack import is_area_attack
from kirby_combat.brief_detail import sightings
from kirby_combat.defences import Defence, answers_to, threatens_a_man
from kirby_combat.judgement import powers_seen

if TYPE_CHECKING:
    from kirby_world.cover import CoverSpot

    from kirby_combat.loop.chooser import PhaseSituation

#: How many cover spots the picture lists.
BEST_COVER = 3

_EPS_M = 1e-6

#: A row that records a Side Effect's happening, not a use on a man.
_NOT_A_USE = "side_effect"


@dataclass(frozen=True)
class ThreatLine:
    enemy_id: str
    power_name: str
    kind: str
    #: Range and line of sight to him now.
    can_reach_me: bool
    #: The area's size in metres; None when the power is not an area.
    area_radius_m: float | None
    answered_by: frozenset[Defence]
    #: Men of his own squad one use would catch; None unless this is an area
    #: and he is in a squad.
    squadmates_it_would_catch: int | None


@dataclass(frozen=True)
class ThreatPicture:
    lines: tuple[ThreatLine, ...]
    enemies_who_can_reach_me: int
    #: enemy_id -> how many standing men of his side that enemy can reach
    #: with any power seen in use (himself included).
    men_she_can_reach: dict[str, int]
    #: The best `BEST_COVER` spots, best first.
    cover: tuple[CoverSpot, ...]
    #: A Half Move in metres (what `cover` was reckoned with; used only for
    #: cover). 0.0 with no map: no cover was reckoned, so no reach was asked.
    reach_m: float


def _kinds_of_use(session: Any) -> dict[tuple[str, str], str]:
    """``{(enemy_id, power name): kind}``: the kind of the FIRST row recording
    each use, in one pass over the log."""
    from kirby_combat.judgement import _used_name

    declared = {e.id: e for e in session.event_log
                if getattr(e, "kind", None) == "ActionDeclared"}
    out: dict[tuple[str, str], str] = {}
    for evt in session.event_log:
        if getattr(evt, "kind", None) != "ActionResolved":
            continue
        if evt.author.type != "combatant":
            continue
        payload = evt.result_payload
        name = _used_name(payload)
        if not name or payload.get("kind") == _NOT_A_USE:
            continue
        kind = payload.get("kind")
        if not kind:
            kind = getattr(declared.get(evt.declaration_event_id), "action_type", None)
        if kind:
            out.setdefault((evt.author.id, name), kind)
    return out


def _view_named(enemy: Any, name: str) -> Any | None:
    for ap in enemy.attacks:
        if (ap.name or "") == name or (getattr(ap, "xmlid", "") or "") == name:
            return ap
    return None


def _can_reach(session: Any, enemy: Any, view: Any, target_id: str,
               sight: dict[tuple[str, str], bool]) -> bool:
    """Whether ``enemy``'s power reaches ``target_id`` from where each stands.
    See the module docstring's REACH ruling. ``sight`` caches line of sight
    per (enemy, man): it does not depend on the power, only on Indirect."""
    from kirby_world.geometry import distance_3d

    from kirby_combat.actions.reach import within_reach
    from kirby_combat.placement import position_of
    from kirby_combat.resolution.line_of_sight import has_line_of_sight

    scene = getattr(session, "scene", None)
    if scene is None:
        return True
    here, there = position_of(scene, enemy.id), position_of(scene, target_id)
    if here is None or there is None:
        return True
    d = distance_3d(here, there)
    ranged = view is not None and bool(
        getattr(view, "is_ranged", (getattr(view, "range_m", 0) or 0) > 0))
    if not ranged:
        area = getattr(view, "area", None) if view is not None else None
        if area is not None:
            return d <= float(area.size_m)
        return within_reach(d, float(enemy.combat_stats().reach_m)).in_reach
    if d > float(view.range_m or 0) + _EPS_M:
        return False
    from kirby_combat.enumeration import _has_modifier

    if _has_modifier(view, "INDIRECT"):
        return True
    key = (enemy.id, target_id)
    if key not in sight:
        sight[key] = has_line_of_sight(scene, here, there)
    return sight[key]


def _squadmates_caught(session: Any, me: Any, radius_m: float,
                       standing: list[str]) -> int:
    """Standing men of ``me``'s side and squad, not himself, within
    ``radius_m`` of him; ``standing`` is his side's standing ids."""
    from kirby_world.geometry import distance_3d

    from kirby_combat.placement import position_of

    scene = getattr(session, "scene", None)
    here = position_of(scene, me.id) if scene is not None else None
    if here is None:
        return 0
    caught = 0
    for cid in standing:
        mate = session.combatants[cid]
        if cid == me.id or getattr(mate, "squad", None) != me.squad:
            continue
        there = position_of(scene, cid)
        if there is not None and distance_3d(here, there) <= radius_m + _EPS_M:
            caught += 1
    return caught


def _cover(situation: PhaseSituation, perceived: list[Any]) -> tuple[tuple, float]:
    from kirby_world.cover import cover_spots

    from kirby_combat.enumeration import can_shoot_from, cover_half_move
    from kirby_combat.placement import position_of

    session, me = situation.session, situation.actor
    scene = getattr(session, "scene", None)
    if scene is None:
        # No map, no cover: nothing to reckon a Half Move against, so none
        # is asked for (a man with no build can still be shown a Brief).
        return (), 0.0
    reach = cover_half_move(me)
    here = position_of(scene, me.id)
    threats = {e.id: p for e in perceived
               if (p := position_of(scene, e.id)) is not None}
    if here is None or not threats:
        return (), reach
    spots = cover_spots(scene, from_pos=here, threats=threats,
                        reach_m=reach, mode="running")
    # ONE DOOR with the menu: a spot that blinds him to every enemy he
    # perceives is not offered as a `move_to_cover`, so it is not listed.
    seen = [e for e in perceived if e.id in threats]
    spots = [s for s in spots if can_shoot_from(scene, s.position, seen)]
    return tuple(spots[:BEST_COVER]), reach


def threat_picture(situation: PhaseSituation) -> ThreatPicture:
    """The threat picture for ``situation.actor``. See the module docstring."""
    from kirby_combat.roster import Roster
    from kirby_combat.side import Side

    session, me = situation.session, situation.actor
    sees = sightings(situation)
    perceived = [e for e in situation.enemies
                 if sees[e.id].perceived and sees[e.id].physical]
    in_squad = getattr(me, "squad", None) is not None
    my_men = Roster(session).standing.get(Side.of(me), [])
    kinds = _kinds_of_use(session)
    sight: dict[tuple[str, str], bool] = {}

    lines: list[ThreatLine] = []
    men_she_can_reach: dict[str, int] = {}
    reaching = 0
    for enemy in perceived:
        mine_reached: set[str] = set()
        reaches_me = False
        for name in powers_seen(session, enemy.id):
            kind = kinds.get((enemy.id, name))
            if kind is None or not threatens_a_man(kind):
                continue
            view = _view_named(enemy, name)
            area = view is not None and is_area_attack(view)
            can_reach_me = _can_reach(session, enemy, view, me.id, sight)
            reaches_me = reaches_me or can_reach_me
            mine_reached |= {
                cid for cid in my_men
                if (can_reach_me if cid == me.id
                    else _can_reach(session, enemy, view, cid, sight))}
            # `size_m` for every shape: for a Cone or Line it is a bound
            # (its length), not an exact reach.
            radius = float(view.area.size_m) if area else None
            lines.append(ThreatLine(
                enemy_id=enemy.id, power_name=name, kind=kind,
                can_reach_me=can_reach_me, area_radius_m=radius,
                answered_by=answers_to(view, kind=kind),
                squadmates_it_would_catch=(
                    _squadmates_caught(session, me, radius, my_men)
                    if area and in_squad else None)))
        men_she_can_reach[enemy.id] = len(mine_reached)
        reaching += reaches_me
    cover, reach_m = _cover(situation, perceived)
    return ThreatPicture(lines=tuple(lines), enemies_who_can_reach_me=reaching,
                         men_she_can_reach=men_she_can_reach, cover=cover,
                         reach_m=reach_m)
