"""Offers that exist because a Phase can now be spent in halves.

* HALF MOVE (6E2 p.26): "A Half Move is defined as moving up to half of a
  character's movement distance ... A character who's made a Half Move can
  perform another Half Phase Action in that Phase". The menu had a Full Move
  (`move`) and a Half Move welded to a strike (`move_strike`), and nothing
  that moved half and left the other half free --- so a man could not step
  up and then pick which blow to throw, step up and Grab, or step behind a
  wall and Hide. One `half_move` per `move` the menu already offers: the same
  mode, the same man, half the distance (`loop/half_phase_resolvers.py`).
* SNAPPING A MAN OUT OF A RAGE (6E1 p.424): "Other circumstances besides
  defeating a target that allow a character to roll to recover from being
  Enraged include ... when someone attempts to snap him out of it (sometimes
  a dangerous task)". Offered to anyone with an Enraged or Berserk ally.
  RULINGS: a Half Phase Action (`action_time.KIND_TIMES`); no range --- a
  shout carries across any field this engine builds; the danger the book
  warns of is the raging man's own next Phase, which is unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from kirby_combat.enumeration import LegalAction, _friendly

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

HALF_MOVE = "half_move"
SNAP_OUT_OF_RAGE = "snap_out_of_rage"


def half_move_offers(session: "CombatSession", actor,
                     menu: Iterable[LegalAction]) -> list[LegalAction]:
    """A Half Move for every Full Move toward a man the menu offers.

    EACH ONE SAYS WHAT IT BUYS A SHOOTER: where it ends and the Range
    Modifier there against the one now (6E2 p.40), because "step up, then
    fire" is the point of a Half Move for anyone with a ranged attack. The
    landing is `closing_move` + `placement.landing_of`, the calls the
    resolver moves him by, and the modifier is `tables.range_penalty`, the
    one the to-hit roll applies, so the page cannot promise a shot the
    engine will not give. (Found 2026-11-10: Plague went 0 for 7 at -4 OCV
    and never closed; his Half Move offer said nothing of range.)
    """
    out: list[LegalAction] = []
    for move in menu:
        if move.kind != "move" or move.target_id is None or move.mode is None:
            continue
        mode = move.mode
        offer = LegalAction(
            action_id=f"{HALF_MOVE}:{mode}:{move.target_id}",
            kind=HALF_MOVE, target_id=move.target_id,
            power_xmlid=None, power_name=None, summary="", mode=mode,
        )
        man = session.combatants[move.target_id]
        offer.summary = (
            f"Half Move toward {_friendly(man)} ({mode}, up to half your "
            f"movement){_what_it_buys(session, actor, offer)}: a Half Phase "
            f"Action, your Phase goes on (6E2 p.26)")
        out.append(offer)
    return out


def _what_it_buys(session: "CombatSession", actor, offer: LegalAction) -> str:
    """", ends 8m from him, Range Modifier 0 there, -4 now (6E2 p.40)"; empty
    when the move cannot be asked about (he or the man is off the map)."""
    from kirby_combat.loop.resolvers import closing_move
    from kirby_combat.placement import landing_of
    from kirby_combat.tables import range_penalty
    from kirby_world.geometry import distance_3d
    from kirby_world.occupancy import position_of

    closing = closing_move(session, actor, offer)
    here = position_of(session.scene, actor.id)
    there = position_of(session.scene, offer.target_id)
    if closing is None or here is None or there is None:
        return ""
    destination, mode, allowance = closing
    outcome = landing_of(session, actor.id, destination,
                         mode=mode, distance_m=allowance)
    if outcome is None:
        return ""
    now = distance_3d(here, there)
    then = distance_3d(outcome.landing, there)
    return (f", ends {then:.0f}m from him, Range Modifier "
            f"{range_penalty(then)} there, {range_penalty(now)} now (6E2 p.40)")


def snap_out_offers(session: "CombatSession", actor, allies: Iterable) -> list[LegalAction]:
    """One offer per raging ally he could call to."""
    from kirby_combat.rage import rage_state

    out: list[LegalAction] = []
    if rage_state(session, actor.id).raging:
        return out
    for ally in allies:
        if ally.id == actor.id:
            continue
        state = rage_state(session, ally.id)
        if not state.raging:
            continue
        word = "Berserk" if state.berserk else "Enraged"
        out.append(LegalAction(
            action_id=f"{SNAP_OUT_OF_RAGE}:{ally.id}",
            kind=SNAP_OUT_OF_RAGE, target_id=ally.id,
            power_xmlid=None, power_name=None,
            summary=(f"Try to snap {_friendly(ally)} out of being {word}: he "
                     f"rolls to recover (6E1 p.424). A Half Phase Action"),
        ))
    return out
