"""Desolidification: switched on, kept up, and what it lets through.

THE RULES (6E1 unless marked):

  * ON AND OFF. "Other Zero Phase Actions include activating a Power,
    turning off a Power" and "Some Zero Phase Actions (such as turning on a
    specific Power) can only be performed once in a Phase" (6E2 p.20). So
    `desolidify` and `drop_desolid` are Zero Phase Actions and the Phase
    comes back to him after either; turning it ON is once a Phase.
  * KEPT UP. Desolidification is a Constant power: it costs END every Phase
    it is on (p.129-130) and comes down on the rules every kept-up power
    shares --- Stunned or Knocked Out as a Segment ends (p.347, 6E2 p.107),
    a Recovery (6E2 p.131), its Multipower slot losing the reserve (p.402),
    not being able to pay. The switch is `switched_powers` and the upkeep
    `kept_up`, so this module owns only what it changes.
  * WHAT REACHES HIM (p.192): "immune to most physical and energy attacks,
    including ones such as Drains and AVADs". Still affecting him: Mental
    Powers (any power on an MCV roll), Sense-Affecting Powers, Presence
    Attacks, attacks through his breathing, an Adjustment Power or Dispel
    bought against Desolidification, and anything with Affects
    Desolidified.
  * WHAT HE REACHES (p.193): "a Desolidified character cannot affect the
    physical world in any way ... His attacks against the physical world
    have no effect. He can't even affect solid targets with Mental Powers
    or Sense-Affecting Powers" --- unless bought with Affects Physical
    World.
  * TWO DESOLID MEN (p.192): they "cannot automatically affect each other
    unless their powers have similar special effects".

RULINGS (each is a reading, not a quote):

  * A Presence Attack is not an attack through the physical world; a
    desolid man may still make one, as one may still be made at him
    (p.192 lists it among what reaches him).
  * "Attacks through breathing" and "an Adjustment Power bought against
    Desolidification" are not readable off a build: nothing marks a power
    as inhaled, or a Drain as aimed at Desolidification. Neither is let
    through. Affects Desolidified is the build's way to say so.
  * Two desolid men: "similar special effects" is not on a build either,
    so between them only what reaches any desolid man reaches.
  * The gate is the MENU: an offer that could not affect its target is not
    offered, the way every other "cannot" in this engine is enforced. An
    Area attack catching a desolid man by the way is NOT gated here (open).

NOT BUILT HERE (open): walking through walls (kirby-world movement), Aborting
to Desolidify (p.193 calls it a defensive action), and shrugging off a
Constant attack by going desolid (p.193).
"""
from __future__ import annotations

from typing import Any

from kirby_combat.switched_powers import Switched, is_on

#: The offer that turns it on, and the one that turns it off (6E2 p.20).
DESOLIDIFY = Switched.DESOLID.terms.on_kind
DROP_DESOLID = Switched.DESOLID.terms.off_kind

AFFECTS_DESOLID = "AFFECTSDESOLID"
AFFECTS_PHYSICAL_WORLD = "AFFECTSPHYSICALWORLD"

#: What reaches a desolid man whatever it was bought with (p.192): the
#: Mental Powers, the Sense-Affecting ones the engine offers, and a
#: Presence Attack.
_MENTAL = frozenset({"mental_blast", "mind_control", "mental_entangle",
                     "mental_illusion", "telepathy", "mind_scan"})
_SENSE_AFFECTING = frozenset({"flash"})
_PRESENCE = frozenset({"presence_attack", "presence_attack_group"})

#: Offers the engine files as no threat that still lay hands on the other
#: man: a Block meets his blow (6E2 p.59). A desolid man's hand passes
#: through a solid one's, and the reverse (RULING from p.192-193).
_CONTACT = frozenset({"block"})


def _has(power: Any, xmlid: str) -> bool:
    from kirby_combat.enumeration import _has_modifier

    return power is not None and _has_modifier(power, xmlid)


def reaches_a_desolid_target(kind: str, power: Any) -> bool:
    """Would an offer of ``kind``, made with ``power`` (its build source, or
    None), affect a desolid man? (p.192)"""
    return (kind in _MENTAL or kind in _SENSE_AFFECTING or kind in _PRESENCE
            or _has(power, AFFECTS_DESOLID))


def reaches_the_solid_world(kind: str, power: Any) -> bool:
    """Would a desolid man's offer of ``kind`` affect a solid target?
    (p.193; a Presence Attack by RULING.)"""
    return kind in _PRESENCE or _has(power, AFFECTS_PHYSICAL_WORLD)


def is_desolid(session, combatant_id: str) -> bool:
    return is_on(session, combatant_id, Switched.DESOLID)


def _source(actor, action) -> Any:
    view = getattr(action, "_attack_view", None)
    if view is None:
        return None
    from kirby_combat.enumeration import source_power_of

    return source_power_of(actor, view)


def across_the_line(session, actor_id: str, menu: list) -> list:
    """Take off the menu what cannot reach its target across the line
    between solid and desolid (p.192-193)."""
    from kirby_combat.defences import NON_THREAT_KINDS

    actor = session.combatants[actor_id]
    gone = {cid for cid in session.combatants if is_desolid(session, cid)}
    if not gone:
        return list(menu)
    kept = []
    for a in menu:
        target = a.target_id
        if (target is None or target == actor_id or target not in session.combatants
                or (a.kind in NON_THREAT_KINDS and a.kind not in _CONTACT)):
            kept.append(a)
            continue
        power = _source(actor, a)
        if target in gone:
            if not reaches_a_desolid_target(a.kind, power):
                continue
        elif actor_id in gone and not reaches_the_solid_world(a.kind, power):
            continue
        kept.append(a)
    return kept
