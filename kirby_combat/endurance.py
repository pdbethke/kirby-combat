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

    Clamped at zero. HERO's rule for spending END you do not have (take
    STUN instead) is NOT implemented and is not claimed to be; this only
    refuses to record a negative pool. The clamp is applied BEFORE the
    event so the number in the log is the number really taken ---
    `apply_vitals_delta` clamps nothing, and a clamp on one side of the
    record and not the other is exactly how a replay drifts.

    THE SPEND IS IN THE LOG. Spends used to be folded straight onto the
    combatant and recorded nowhere, so a fight rebuilt from its rows had
    everybody's wind back.
    """
    from kirby_combat.vitals import record_vitals_change

    combatant = session.combatants.get(combatant_id)
    if combatant is None:
        return session
    have = int(getattr(combatant.state, "current_end", 0) or 0)
    spend = min(cost, max(0, have))
    if spend <= 0:
        return session
    session, _ = record_vitals_change(
        session, combatant_id, end=-spend, reason="end_spent",
    )
    return session


def pay_for_movement(session, combatant_id: str, *, mode: str, used_m: float,
                     template):
    """Charge him for ``used_m`` metres of ``mode`` (6E1 p.158), where the
    campaign counts END. Reads his full move's END off `movement_view`."""
    combatant = session.combatants.get(combatant_id)
    if combatant is None or not tracks_endurance(template, combatant):
        return session
    caps = [c for c in combatant.movement_view() if c.mode == mode]
    if not caps:
        raise ValueError(
            f"{combatant_id!r} moved by {mode!r} and has no such movement")
    cap = max(caps, key=lambda c: c.combat_m)
    return spend_end(session, combatant_id, movement_end(
        cap.end_cost, used_m=used_m, combat_m=cap.combat_m))


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
