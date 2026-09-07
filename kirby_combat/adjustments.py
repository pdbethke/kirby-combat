"""Adjustments applied — what an Aid or a Drain actually changes.

THE GAP THIS CLOSES. Adjustment has had every piece but one. `AdjustmentApplied`
was emitted, `session/effects.py` folded it correctly, and (since 2026-09-07)
`AdjustmentFaded` reduced it every Turn. And a grep for
``adjustment_delta``/``adjustments_for`` outside `effects.py` itself returned
NOTHING: no stat consumer read the fold, so an Aid raised nothing and a Drain
lowered nothing. The whole chain kept books on an effect that never happened.

WHY A SESSION-AWARE READ AND NOT A MUTATED COMBATANT. A characteristic is
build data --- `combat_stats()` derives it from the hero --- and an Adjustment
is a temporary condition of the FIGHT, exactly like being Stunned. Writing
it onto the combatant would put a fight's state into the build's shape and
lose the distinction between "this character has DEX 20" and "this character
has DEX 20 and is currently Drained 4".

So this follows the seam `cv_modifiers.py` already established for Stunned:
the base comes from the build, the session supplies the modifier, and the
two are composed at the point of use.

WHAT THIS DOES NOT REACH, said plainly. Every caller that reads
``combatant.combat_stats().X`` directly still gets the unadjusted value.
The CV path (`effective_ocv_for` and friends) and the Stunning check are
wired below because they are what decides a fight; the rest of the engine
is not rewritten to thread a session it does not have. A caller that wants
an adjusted characteristic asks for one.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kirby_combat.session.effects import adjustment_delta

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

#: The CV keys `cv_modifiers._effective_cv` works in, mapped to the
#: characteristic xmlid an Adjustment would name. Kept explicit rather than
#: upper-casing the key, because OCV and DCV are their own characteristics
#: in 6E and not abbreviations of something else.
CV_STATS = {"ocv": "OCV", "dcv": "DCV", "omcv": "OMCV", "dmcv": "DMCV"}


def net_adjustment(session: "CombatSession", combatant_id: str, stat: str) -> int:
    """The live net Adjustment on one characteristic, signed.

    Positive from an Aid, negative from a Drain, zero when nothing is
    active or it has faded out. Case-insensitive on ``stat`` because the
    xmlid an Adjustment records ("STUN") and the CV key a caller works in
    ("dcv") are written differently in different parts of this engine.
    """
    return adjustment_delta(session, combatant_id, (stat or "").upper())


def effective_characteristic(
    session: "CombatSession", combatant_id: str, stat: str, base: int,
) -> int:
    """``base`` plus whatever Aid or Drain is live on it.

    FLOORED AT ZERO. 6E1 p.139: a Drain reduces a characteristic, and a
    characteristic does not go negative --- a Drained DEX of -3 is not a
    thing the rules describe, and letting one through would put a negative
    into every roll derived from it. `compute_drain` already caps a single
    Drain by the target's current value; this floor is what holds when two
    of them stack.
    """
    return max(0, int(base) + net_adjustment(session, combatant_id, stat))


def adjusted_con(session: "CombatSession", combatant) -> int:
    """The CON a Stunning check should read (6E2 p.106).

    Drained CON is one of the sharpest things an Adjustment does: Stunning
    is "STUN done by a single attack exceeds his CON", so lowering CON
    makes a target easier to Stun with attacks that would otherwise fall
    short. That is the whole point of Draining it, and it was inert.
    """
    return effective_characteristic(
        session, combatant.id, "CON", int(combatant.combat_stats().con),
    )
