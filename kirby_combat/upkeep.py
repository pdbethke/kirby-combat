"""Keeping a power up: the rules every maintained power shares.

A power that stays on the board after the Phase it was used in is kept up
by its user, and the books state once, for all of them, what that costs and
what takes it down. Four homes maintain one: `lingering` (Constant
attacks), `standing_areas` (Constant zones and Damage Shields),
`kept_up` (Darkness fields and Images). Each carried its own copy of the
slot check and none spent a Charge; this module is the one copy.

THE RULES, page by page (6E1 unless marked):

  * p.129: "Once a character has turned a Constant Power on, all he has to
    do is spend END each Phase to keep it activated ... the character must
    maintain a Line Of Sight to the location of the Power and pay the END
    for the Power on each of his Phases." p.130: that END is "paid when the
    character's Phase begins, before he does anything else".
  * p.129 (Sapphire): two uses of one Constant power are two things to
    keep up --- "Sapphire has to pay END to maintain each use of the
    Constant Power, for a total of 20 END per Phase". So nothing here
    counts uses; each pays its own way.
  * p.369: "Each Charge normally only lasts for one Phase"; p.403:
    "Constant Powers require one Charge per Phase, as usual." A Charged
    power keeps going on Charges, one each Phase, not on END.
  * p.402: "If he changes the reserve/Pool allocation to another slot while
    that Constant or Persistent Power is in use, the power immediately
    ceases to operate unless it's bought Uncontrolled, with Continuing
    Charges, or with some similar Power Modifier ... He must keep the
    Framework's reserve or Pool allocated to that slot to maintain the
    Constant or Persistent Power." (p.413 says the same of a VPP.)

NOT BUILT, and so never offered (`not_built`): the three modifiers p.402
names as exceptions change how a power ENDS, and nothing here carries them.
Uncontrolled (p.354) runs on a pool of END its user chooses and stops on "a
reasonably common and obvious set of circumstances" written on the build;
Continuing Charges (p.371-372) last by the Time Chart; Fuel Charges (p.373)
burn by the second. Kept up by the plain rule they would end the way the
modifier was bought to prevent, which is a wrong answer, not an
approximation.

RULING, carried over unchanged from `lingering` and `standing_areas`: a man
who cannot pay stops rather than burn STUN for END (6E2 p.133 permits it).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class UpkeepEnd(str, Enum):
    """Why something kept up came down. The values are on the wire
    (`DarknessEnded.reason`, an Image's ``image_ended`` row)."""

    DROPPED = "dropped"                               # 6E2 p.20
    NO_END = "could_not_pay_end"                      # 6E1 p.129, p.188
    NO_CHARGES = "out_of_charges"                     # 6E1 p.369, p.403
    LOST_LINE_OF_SIGHT = "lost_line_of_sight"         # 6E1 p.129
    OWNER_STUNNED = "owner_stunned_or_out"            # 6E1 p.347, 6E2 p.107
    RECOVERED = "owner_took_a_recovery"               # 6E2 p.131
    SLOT_SWITCHED = "slot_switched_off"               # 6E1 p.402
    POWER_NOT_ON_BUILD = "power_not_on_build"


# --------------------------------------------------------------- the slot

def framework_slot(combatant: Any, power: Any) -> tuple[str, str] | None:
    """``(framework id, slot id)`` when ``power`` is a slot in a Multipower
    or VPP, else None.

    An attack view carries both (`AttackPower.framework_id`/``slot_id``). A
    build power does not, so it is found among the frameworks' slots by its
    own id --- the same id `HeroCombatant.framework_view` writes.
    """
    fid = str(getattr(power, "framework_id", "") or "")
    sid = str(getattr(power, "slot_id", "") or "")
    if fid and sid:
        return fid, sid
    pid = str(getattr(power, "id", "") or "")
    if not pid or combatant is None:
        return None
    for frame in combatant.framework_view() or []:
        for slot in frame.slots:
            if slot.slot_id == pid:
                return frame.framework_id, slot.slot_id
    return None


def slot_on(combatant: Any, power: Any, slot_allocation) -> bool:
    """Is ``power``'s slot holding the reserve, by the menu's
    ``slot_allocation`` (`framework.allocation_for`)? The same answer
    `slot_still_allocated` gives from the combatant's state, for enumeration, which is
    handed the allocation rather than the fight.

    6E1 p.402: "When a character allocates or re-allocates reserve/Pool
    points to a Constant or Persistent Power, he must then turn the power
    on" --- the allocation comes first, so a Constant slot that is not
    allocated is not offered; switching to it is the ``reallocate`` offer.
    """
    where = framework_slot(combatant, power)
    if where is None or not slot_allocation:
        return True
    entry = slot_allocation.get(where[0])
    if entry is None:
        # not opened: the build as written
        return True
    return where[1] in entry[2]


def slot_still_allocated(session, owner_id: str, power: Any) -> bool:
    """6E1 p.402: he "must keep the Framework's reserve or Pool allocated to
    that slot to maintain" it. A power in no Framework always is.

    The slot is allocated while it holds points (6E1 p.404-406): a slot cut
    to 0 is off. A framework not yet opened is as the build has it
    (`framework.slot_points_for` is None); that exists only during setup.
    """
    from kirby_combat.framework import slot_points_for

    owner = session.combatants.get(owner_id)
    where = framework_slot(owner, power)
    if where is None:
        return True
    framework_id, slot_id = where
    points = slot_points_for(owner, framework_id)
    return points is None or points.get(slot_id, 0) > 0


# ------------------------------------------------------------ not built

def not_built(power: Any) -> list[str]:
    """What on this power's build changes how it is kept up and is not
    carried out here. Non-empty means the power is not offered."""
    from kirby_combat.power_modifiers import _adders, _find

    out: list[str] = []
    if _find(power, "UNCONTROLLED") is not None:
        out.append("Uncontrolled (6E1 p.354)")
    charges = _find(power, "CHARGES")
    if charges is not None:
        adders = _adders(charges)
        if "CONTINUING" in adders:
            out.append("Continuing Charges (6E1 p.371-372)")
        if "FUEL" in adders:
            out.append("Fuel Charges (6E1 p.373)")
    return out


# ------------------------------------------------------------- the price

def end_of(power: Any) -> int:
    """END one use of ``power`` costs, read off its sheet.

    A build power carries the cost engine's own END column (``end_usage``):
    0 for a 0 END power or a Charged one (6E1 p.369), the Reduced or
    Increased figure where it was bought. `endurance.end_cost` prices an
    attack view, which carries that same column as ``end_per_use``, and
    otherwise falls back to Active Points --- which charged a 0 END Darkness
    for every Phase it stood.
    """
    from kirby_combat.endurance import end_cost

    sheet = getattr(power, "end_usage", None)
    if sheet is not None:
        return int(sheet)
    return end_cost(power)


def has_a_charge(session, owner_id: str, power: Any) -> bool:
    """A use left (6E1 p.334), counted the way `charges.spent_charges`
    counts every other use."""
    from kirby_combat.charges import has_charges_left, spent_charges

    return has_charges_left(power, spent_charges(session, owner_id))


def spend_a_charge(session, owner_id: str, power: Any, *, why: str):
    """One Charge of ``power`` gone, on the log (`ChargeSpent`)."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ChargeSpent, make_author_engine

    return apply_event(session, ChargeSpent(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(UTC), author=make_author_engine(),
        combatant_id=owner_id,
        power_source_id=str(getattr(power, "id", "") or getattr(power, "source_id", "") or ""),
        reason=why,
    ))


def charged(power: Any) -> bool:
    from kirby_combat.charges import charge_pool

    return charge_pool(power) is not None


def _charge_source(session, owner_id: str, power: Any) -> Any:
    """The build power that carries ``power``'s Charges. A build power is
    its own; an attack view (no modifier list of its own) is traced back to
    the build object it came from (`enumeration.source_power_of`), which is
    what `charges.spent_charges` counts a use against."""
    if getattr(power, "assigned_modifiers", None) is not None:
        return power
    from kirby_combat.enumeration import source_power_of

    owner = session.combatants.get(owner_id)
    return source_power_of(owner, power) if owner is not None else None


def pay_for_the_phase(session, owner_id: str, power: Any, *, template,
                      end: int | None = None):
    """Pay to keep ``power`` up this Phase: a Charge if it has them (6E1
    p.369, p.403), and its END (p.129-130). ``(session, None)`` when paid,
    ``(session, reason)`` when he cannot --- in which case nothing is spent.

    ``end`` overrides the sheet's price for a caller that already has the
    right figure (an attack view's ``end_per_use``)."""
    from kirby_combat.actions.recording import _spend_attack_end
    from kirby_combat.endurance import end_available

    source = _charge_source(session, owner_id, power)
    is_charged = source is not None and charged(source)
    if is_charged and not has_a_charge(session, owner_id, source):
        return session, UpkeepEnd.NO_CHARGES
    cost = end_of(power) if end is None else int(end)
    left = end_available(session, owner_id, power=power, template=template)
    if cost and left is not None and left < cost:
        # RULING: he stops rather than burn STUN for END (module doc).
        return session, UpkeepEnd.NO_END
    if is_charged:
        session = spend_a_charge(session, owner_id, source, why="upkeep")
    session = _spend_attack_end(session, session.combatants[owner_id], cost,
                                template, power=power)
    return session, None


# ---------------------------------------------------------- sight of it

def sees(session, owner_id: str, point: tuple[float, float, float]) -> bool:
    """6E1 p.129: "maintain a Line Of Sight to the location of the Power"."""
    from kirby_world.geometry import line_of_sight_clear
    from kirby_world.scene import Position

    scene = getattr(session, "scene", None)
    if scene is None:
        return True                       # no map: nothing can block it
    here = scene.combatant_positions.get(owner_id)
    if here is None:
        return False
    return line_of_sight_clear(here, Position(*point), scene.walls or [])


def stunned_or_out(session, owner_id: str) -> bool:
    """6E1 p.347 / 6E2 p.107: Stunned or Knocked Out NOW, as the Segment
    ends --- the ``stunned`` status, not `statuses.stunned_or_recovering_for`,
    whose window runs on through the Segment he recovered in ("his Constant
    Powers won't turn off, since he won't still be Stunned at the end of the
    Segment", 6E2 p.107)."""
    from kirby_combat.enumeration import is_down
    from kirby_combat.statuses import statuses_for

    owner = session.combatants.get(owner_id)
    return owner is None or is_down(owner) or bool(
        {"stunned", "knockedOut"} & statuses_for(session, owner_id))
