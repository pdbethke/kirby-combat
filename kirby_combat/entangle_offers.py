"""What the menu offers around an Entangle, beyond the victim's escape ladder.

1. AN OUTSIDE ATTACK ON THE ENTANGLE (6E1 p.218-219). "A character may target
   most types of Entangle specifically, without damaging the character inside
   it ... at -3 OCV. Typically an Entangle targeted in this manner has DCV 0".
   And for a Mental Paralysis: "Another character can target a Mental
   Paralysis without targeting its victim; the Mental Paralysis has DMCV 3",
   and only "Mental Blasts (but not other Mental Powers)" affect it, against
   its Mental Defense. The deleted api driver did neither; a man glued to the
   floor could be freed only by himself.

   NOT OFFERED, by the book or because it is not built:
   * Takes No Damage From Attacks +1 (STR_ONLY): "cannot be attacked,
     damaged, or affected by outside attackers at all" (p.221).
   * Takes No Damage +1/4 or +1/2 (LIMITED / ALL), and Entangle And
     Character Both Take Damage: the targeted attack carries on into the man
     inside ("the damage affects the Entangle and then the Entangled
     character", p.221; "he and the Entangle both take damage", p.220). The
     overflow onto the victim is not built, so neither is offered.
   * An Area, Autofire, Constant or Damage Over Time power: one plain shot.
   RULING: offered for an ALLY's Entangle. Freeing a friend is what the rule
   is for; breaking an enemy out of his bonds is a gift nobody asks for.

2. THE VICTIM'S OWN LADDER, narrowed: a +1 Takes No Damage Entangle leaves
   him "only ... his STR (or EGO, for Mental Paralysis Entangles)", so no
   escape by attacking it (`ladder_for`).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from kirby_combat.enumeration import LegalAction, _friendly, is_down

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

ATTACK_ENTANGLE = "attack_entangle"

#: 6E1 p.218: "at -3 OCV" against "DCV 0".
TARGETED_ENTANGLE_OCV = -3
TARGETED_ENTANGLE_DCV = 0
#: 6E1 p.219: "the Mental Paralysis has DMCV 3 for this purpose".
TARGETED_PARALYSIS_DMCV = 3


def _plain(power) -> bool:
    """One shot of an ordinary power: nothing the targeted-Entangle resolver
    does not carry out."""
    return (int(getattr(power, "damage_dice", 0) or 0) > 0
            and getattr(power, "area", None) is None
            and getattr(power, "autofire", None) is None
            and getattr(power, "damage_over_time", None) is None
            and not getattr(power, "constant", False))


def _powers(menu: Iterable[LegalAction]) -> list:
    """The distinct powers his own attack offers carry, by source id."""
    seen: dict[str, object] = {}
    for a in menu:
        view = a._attack_view
        if a.kind in ("attack", "strike", "mental_blast") and view is not None:
            seen.setdefault(str(getattr(view, "source_id", None) or view.xmlid), view)
    return list(seen.values())


def _in_reach(session, actor, victim, power, reach_m: float) -> bool:
    from kirby_combat.loop.run import distances_from
    from kirby_combat.perception import perceive

    seen = perceive(actor, victim, session.scene)
    mental = (getattr(power, "xmlid", "") or "").upper() == "MENTALBLAST"
    if not (seen.targetable_mental if mental else seen.targetable_physical):
        return False
    if mental:
        return True                      # what he perceives mentally, he can reach
    distance = (distances_from(session.scene, actor, [victim]) or {}).get(victim.id)
    if distance is None:
        return True                      # a fight on no map gates no range
    if getattr(power, "is_ranged", False):
        return distance <= float(getattr(power, "range_m", 0) or 0)
    return distance <= max(reach_m, float(getattr(power, "reach_m", 0) or 0))


def attack_entangle_offers(session: "CombatSession", actor, allies: Iterable,
                           menu: Iterable[LegalAction], reach_m: float) -> list[LegalAction]:
    """Offers to shoot or strike an ally's Entangle off him."""
    from kirby_combat.actions.entangle import Entangle, Transparency

    menu = list(menu)
    powers = [p for p in _powers(menu) if _plain(p)]
    out: list[LegalAction] = []
    for ally in allies:
        if ally.id == actor.id or is_down(ally):
            continue
        for paralysis in (False, True):
            hold = Entangle.held(session, ally.id, mental_paralysis=paralysis)
            if hold is None:
                continue
            if paralysis:
                if hold.transparency is Transparency.STR_ONLY:
                    continue
            elif hold.transparency is not Transparency.NONE or hold.both_take_damage:
                continue
            for power in powers:
                blast = (power.xmlid or "").upper() == "MENTALBLAST"
                if paralysis and not blast:
                    continue             # "Mental Blasts (but not other Mental Powers)"
                if not paralysis and (blast or getattr(power, "is_mental", False)):
                    continue             # a mental power does not touch a physical Entangle
                if not _in_reach(session, actor, ally, power, reach_m):
                    continue
                which = "Mental Paralysis" if paralysis else "Entangle"
                cv = (f"against DMCV {TARGETED_PARALYSIS_DMCV}" if paralysis
                      else f"at {TARGETED_ENTANGLE_OCV} OCV against DCV "
                           f"{TARGETED_ENTANGLE_DCV}")
                out.append(LegalAction(
                    action_id=(f"{ATTACK_ENTANGLE}:{'paralysis' if paralysis else 'physical'}"
                               f":{ally.id}:{getattr(power, 'source_id', None) or power.xmlid}"),
                    kind=ATTACK_ENTANGLE, target_id=ally.id,
                    power_xmlid=power.xmlid, power_name=power.name,
                    summary=(f"Break {_friendly(ally)} out: {power.name or power.xmlid} "
                             f"at the {which} holding him ({cv}; BODY {hold.body}, "
                             f"{'MD ' + str(hold.md) if paralysis else f'DEF {hold.pd}/{hold.ed}'}"
                             f"; 6E1 p.218-219)"),
                    _attack_view=power,
                ))
    return out


def ladder_for(session: "CombatSession", actor_id: str,
               menu: Iterable[LegalAction]) -> list[LegalAction]:
    """His escape offers, less the ones his Entangle was bought to refuse."""
    from kirby_combat.actions.entangle import Entangle, Transparency

    paralysis = Entangle.held(session, actor_id, mental_paralysis=True)
    if paralysis is None or paralysis.transparency is not Transparency.STR_ONLY:
        return list(menu)
    # 6E1 p.221: "only ... EGO, for Mental Paralysis Entangles".
    return [a for a in menu if not a.action_id.startswith("escape:paralysis:attack:")]
