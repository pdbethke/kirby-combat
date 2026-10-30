"""What a power costs to use (6E1 p.132).

NOBODY IN THIS ENGINE HAD EVER SPENT END ON AN ATTACK. `actions/base.py`
computed `end_spent = max(1, power.damage_dice)`, put it on the
`AttackResult`, and no caller subtracted it --- so a fighter threw an 8d6
Blast and finished the Phase at the END he started with, while the engine
implemented Recovery, Post-Segment 12 Recovery and a REC characteristic
with nothing to recover from.

THE RULE, quoted. 6E1 p.132: "Every Phase such a Power is turned on, it
costs the character 1 END for every 10 Active Points of Power used ...
The minimum END cost for a power that costs END is 1 END per Phase,
regardless of how few Active Points of the Power a character uses." And
the rounding, with the book's own two examples: "The standard rounding
rules apply to END cost calculations. A character using a 15 Active Point
ability pays 1 END; a character using a 46 Active Point ability pays 5
END."

15 -> 1 is the half rounding DOWN, because HERO rounds in the character's
favour and this is a cost. 46 -> 5 is 4.6 rounding up. Both are tests.

ACTIVE POINTS, NOT DICE. The old proxy read the dice count, which is
roughly double: an 8d6 Blast is 40 Active Points and costs 4 END, not 8.
`AttackPower.active_points` has carried the cost engine's own figure since
`hero_view` line 992 and nothing used it for this.

WHAT IS FREE. A power on Charges, and one bought with Reduced Endurance
(0 END). `hero_view` line 1933 has been parsing the second for a long time
and throwing it away, with the comment `# noqa: F841 (END calc TBD)`.
That is why the O.K. Corral was the wrong place to notice the missing
spend: a Colt Peacemaker runs on Charges, so those nine men were right to
end the fight at full END.

NO ACTIVE POINTS IS NOT FREE. A hand-built power with no cost-engine
figure costs the minimum, because returning 0 would make every synthetic
fixture in the suite a perpetual-motion machine.
"""
from __future__ import annotations

import math
from typing import Any

#: 6E1 p.132. One END per ten Active Points.
ACTIVE_POINTS_PER_END = 10

#: "The minimum END cost for a power that costs END is 1 END per Phase."
MINIMUM_END = 1


def costs_end(power: Any) -> bool:
    """Whether using this power costs the character anything at all.

    Charges and Reduced Endurance (0 END) are the two ways an attack in
    this engine is free. Both are read off the build; neither is inferred
    from the shape of the power.
    """
    if getattr(power, "reduced_end", False):
        return False
    charges = getattr(power, "charges", None)
    # NONE IS NOT ZERO, the same distinction `charges.charges_on` draws:
    # "unlimited" and "has a clip" must never be the same answer.
    return charges is None


def end_cost(power: Any) -> int:
    """END this power costs for one Phase's use (6E1 p.132)."""
    if not costs_end(power):
        return 0
    active = int(getattr(power, "active_points", 0) or 0)
    if active <= 0:
        return MINIMUM_END
    return end_for_points(active) * end_multiplier(power)


def _round_cost(value: float) -> int:
    """HERO rounds to nearest and gives the half to the character. This is
    a cost, so the half rounds DOWN -- which is the book's own 15 -> 1."""
    whole = math.floor(value)
    return whole + (1 if value - whole > 0.5 else 0)


def end_for_points(points: float) -> int:
    """END for using ``points`` Active Points' worth of a power (6E1 p.132):
    one per ten, rounded as above, never under the minimum."""
    return max(MINIMUM_END, _round_cost(points / ACTIVE_POINTS_PER_END))


def movement_end(full_end: int, *, used_m: float, combat_m: float) -> int:
    """END for moving ``used_m`` with a mode whose full move costs ``full_end``.

    6E1 p.158: "If a character uses less than his full meters of movement,
    typically he only pays END proportionately (for example, he pays half
    the power's full END cost when making a Half Move)." At least the
    minimum when anything is owed (6E1 p.132). Metres past ``combat_m`` are
    a Push, paid for by the Push's own END (6E2 p.135), so the share stops
    at the full move.
    """
    if full_end <= 0 or used_m <= 0 or combat_m <= 0:
        return 0
    share = min(used_m, combat_m) / combat_m
    return max(MINIMUM_END, _round_cost(full_end * share))


def tracks_endurance(template, combatant) -> bool:
    """Whether this campaign counts END at all.

    THE TEMPLATES HAVE SAID THIS SINCE THEY WERE WRITTEN and nothing read
    them: `RAW_SUPERHEROIC` ships `manage_endurance=False` ("END
    optional"), `RAW_HEROIC` ships `manage_endurance=True` ("grittier; hit
    locations and END tracked"). That is the genre split -- four-colour
    games hand-wave END, gritty ones count it -- and charging END
    unconditionally quietly overrode a policy the data already stated.

    `manage_endurance_npc` is the second half of the same pair, and
    `StatBlockCombatant.is_npc` was likewise read by nothing: a table that
    tracks END for the player characters and not for the mooks is an
    ordinary house rule, and both fields exist to express it.

    Moved here from `actions/recording.py` when movement began paying END:
    an attack and a move must ask the campaign the same question.
    """
    if template is None:
        return True
    if getattr(combatant, "is_npc", False):
        return bool(getattr(template, "manage_endurance_npc", False))
    return bool(getattr(template, "manage_endurance", False))


def spend_end(session, combatant_id: str, cost: int):
    """Take END off a combatant --- the one door for a spend.

    WHAT HE HAS, THEN STUN (6E2 p.133). "A character who runs out of END
    ... and still wishes to perform Actions may use STUN as END. The
    character takes 1d6 STUN Only damage for every 2 'END' (or fraction
    thereof) used, and no defense is allowed against this damage. Yes,
    characters can Knock themselves Out using this rule ... Characters
    cannot spend END below 0." So the END he has is spent, and whatever is
    left of ``cost`` is rolled off the session's own dice as STUN
    (``reason="stun_for_end"``); he is Knocked Out the moment that takes him
    to 0, as any STUN loss does. Before this, the spend was clamped at zero
    and nothing more was charged, so a man out of END fired for free for
    the rest of the fight.

    It is his choice ("may"), and a seat that does not want to pay it does
    not choose the power: this is the price of the choice, not a gate on it.
    An Endurance Reserve never pays in STUN (6E1 p.208; `spend_from`).

    THE SPEND IS IN THE LOG, both halves, so a fight rebuilt from its rows
    has everybody's wind back.
    """
    from kirby_combat.vitals import record_vitals_change

    combatant = session.combatants.get(combatant_id)
    if combatant is None or cost <= 0:
        return session
    have = int(getattr(combatant.state, "current_end", 0) or 0)
    spend = min(cost, max(0, have))
    if spend > 0:
        session, _ = record_vitals_change(
            session, combatant_id, end=-spend, reason="end_spent",
        )
    short = cost - spend
    if short > 0:
        if session.dice_roller is None:
            raise ValueError(
                f"{combatant_id!r} owes {short} END in STUN (6E2 p.133) and the "
                "session has no dice_roller to roll it with")
        stun = sum(session.dice_roller.roll_dice(math.ceil(short / 2)))
        session, _ = record_vitals_change(
            session, combatant_id, stun=-stun, reason="stun_for_end",
        )
    return session


def pay_for_movement(session, combatant_id: str, *, mode: str, used_m: float,
                     template):
    """Charge him for ``used_m`` metres of ``mode`` (6E1 p.158), where the
    campaign counts END, from the pool the mode draws on (`pay_end`). Reads
    his full move's END off `movement_view`."""
    combatant = session.combatants.get(combatant_id)
    if combatant is None:
        return session
    caps = [c for c in combatant.movement_view() if c.mode == mode]
    if not caps:
        raise ValueError(
            f"{combatant_id!r} moved by {mode!r} and has no such movement")
    cap = max(caps, key=lambda c: c.combat_m)
    return pay_end(session, combatant_id, movement_end(
        cap.end_cost, used_m=used_m, combat_m=cap.combat_m),
        power=cap, template=template)


# ---------------------------------------------------------------------------
# Endurance Reserves (6E1 p.207-208)
# ---------------------------------------------------------------------------

def draws_on_reserve(power) -> bool:
    """Is this power (an `AttackPower` or a `MovementCapability`) bought to
    "draw energy from the Reserve" rather than from his own END? ``None``
    is a spend with no power behind it --- STR, an EGO escape --- and those
    are always his own (6E1 p.43, p.219)."""
    return power is not None and bool(getattr(power, "uses_end_reserve", False))


def reserve_end(session, combatant_id: str, reserve) -> int:
    """END left in one of his Reserves: its storage, plus every
    `EnduranceReserveChanged` the fight has written against it."""
    total = int(reserve.max_end)
    for evt in session.event_log:
        if (getattr(evt, "kind", None) == "EnduranceReserveChanged"
                and evt.combatant_id == combatant_id
                and evt.reserve_id == reserve.id):
            total += int(evt.end)
    return total


def drawing_reserve(session, combatant_id: str):
    """The Reserve a reserve-powered power draws on, and its END left.

    RULING on 6E1 p.207: "If a character has two or more Endurance Reserves
    that could supply END to the same power, the character can choose
    whichever one he wants." The build does not say which supplies which,
    so every one of his Reserves can, and he draws on the fullest --- the
    choice that keeps the most powers running. Ties go to the build's
    order.

    Raises for a man with a reserve-powered power and no Reserve at all:
    HD will not write that, and drawing his own END instead would be the
    silent substitution 6E1 p.207 forbids.
    """
    reserves = list(session.combatants[combatant_id].reserves())
    if not reserves:
        raise ValueError(
            f"{combatant_id!r} has a power that draws on an Endurance Reserve "
            "and owns no Endurance Reserve")
    best = max(reserves, key=lambda r: reserve_end(session, combatant_id, r))
    return best, reserve_end(session, combatant_id, best)


def end_available(session, combatant_id: str, *, power, template) -> int | None:
    """END he can put into ``power`` now, or None when the campaign does not
    count END (nothing then limits him)."""
    combatant = session.combatants[combatant_id]
    if not tracks_endurance(template, combatant):
        return None
    if draws_on_reserve(power):
        return drawing_reserve(session, combatant_id)[1]
    return int(getattr(combatant.state, "current_end", 0) or 0)


def _record_reserve_change(session, combatant_id: str, reserve_id: str,
                           end: int, reason: str):
    import uuid
    from datetime import datetime, timezone

    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import (
        EnduranceReserveChanged,
        make_author_engine,
    )

    return apply_event(session, EnduranceReserveChanged(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id=combatant_id, reserve_id=reserve_id, end=int(end),
        reason=reason,
    ))


def pay_end(session, combatant_id: str, cost: int, *, power, template):
    """Pay ``cost`` END for ``power`` from the pool it draws on.

    THE ONE DOOR. A power bought to draw on an Endurance Reserve is paid
    from the Reserve and never from him: 6E1 p.207, "A power can normally
    only draw energy from one or the other"; and "A character cannot spend
    STUN in the place of Endurance Reserve END" --- so a Reserve's spend is
    clamped at what it holds, exactly as his own is (`spend_end`). Nothing
    is paid where the campaign does not count END.
    """
    combatant = session.combatants.get(combatant_id)
    if combatant is None or cost <= 0 or not tracks_endurance(template, combatant):
        return session
    return spend_from(session, combatant_id, cost, power=power)


def spend_from(session, combatant_id: str, cost: int, *, power):
    """Take ``cost`` from the pool ``power`` draws on, whatever the campaign
    says about routine END --- for what is always paid, a Push (6E2 p.133:
    "Characters can Push powers that get their END from an Endurance
    Reserve", 6E1 p.207). `pay_end` is this behind the campaign's switch."""
    if cost <= 0 or combatant_id not in session.combatants:
        return session
    if not draws_on_reserve(power):
        return spend_end(session, combatant_id, cost)
    reserve, have = drawing_reserve(session, combatant_id)
    spend = min(int(cost), max(0, have))
    if spend <= 0:
        return session
    return _record_reserve_change(session, combatant_id, reserve.id, -spend,
                                  "end_spent")


def recover_reserves(session):
    """Each Reserve Recovers its REC, at the Post-Segment 12 Recovery.

    6E1 p.207: "An Endurance Reserve normally Recovers its REC in END each
    Turn ... Endurance Reserves cannot Recover more frequently than once per
    Turn", and a Reserve slowed by a Limitation on its REC does so every
    ``recovers_every_turns`` Turns (`hero_view._reserve_recovers_every`).
    Never past its storage. Whether he is conscious does not matter: "an
    Endurance Reserve can keep using its REC to Recover its END even if the
    character is Knocked Out".
    """
    turn = int(session.timeline.turn)
    for combatant_id in list(session.combatants):
        for reserve in session.combatants[combatant_id].reserves():
            every = reserve.recovers_every_turns
            if every is None or turn % every:
                continue
            room = reserve.max_end - reserve_end(session, combatant_id, reserve)
            gain = min(int(reserve.rec), room)
            if gain > 0:
                session = _record_reserve_change(
                    session, combatant_id, reserve.id, gain, "recovery")
    return session


def end_multiplier(power: Any) -> int:
    """Increased Endurance Cost's multiple, or 1 (6E1 p.376).

    "A power with this Limitation is so strenuous to use that it costs a
    character more than the normal 1 END per 10 Active Points." The book
    multiplies the ROUNDED cost: Pulsar's 4d6 bought at x2 END costs 4 END
    (6E1 p.368: "4+4+6+10 = 24 END" for 8d6 normal, 4d6 x2, 4d6 x3, 4d6
    x5). The deleted api driver charged x2 whatever the build said.
    """
    spec = getattr(power, "increased_end", None)
    if spec is None:
        return 1
    if spec.multiplier < 1:
        raise ValueError(
            f"power {getattr(power, 'name', '?')!r} carries an Increased "
            f"Endurance Cost the engine cannot read ({spec.unbuilt}); it "
            "should not have been offered"
        )
    return int(spec.multiplier)
