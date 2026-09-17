"""How badly hurt a combatant is — one rung ladder, one place.

NOT A BOOK NUMBER. 6E gives no "wounded" or "critical" state: a character
is up, Stunned, unconscious at 0 STUN, or dying at 0 BODY (6E1 p.421), and
nothing in between is named. The half-STUN and quarter-STUN rungs below are
THIS ENGINE'S JUDGEMENT about when a fighter should stop trading blows, and
they are said out loud here rather than hidden in whichever module needed
them first.

WHICH IS EXACTLY WHAT HAD HAPPENED. The same five lines of arithmetic --
the two thresholds, the rounding, the `body_pct <= 0 or stun_pct <=
critical` test and the `stun_pct < wounded` test -- stood in three separate
places, one per consumer. Three copies of a judgement is three judgements:
the day one of them moves a rung, a fighter is "critical" to the tactic
that tells him to take cover and "wounded" to whatever else asks, and
nothing in either place says they were ever meant to agree.

AND ENUMERATION HELD THE FOURTH STATEMENT OF IT, now closed.
`enumerate_actions` offers a Recover "when the actor is wounded (<½
STUN)" and used to decide that with its own `current_stun < max_stun //
2` --- integer-division arithmetic, not the rounded percentage here, so
the two really could disagree (max_stun 45: `//2` is 22 and half is
22.5, and a man at 22 was "wounded" to the menu and "healthy" to his
tactics). It asks `classify_health` now. A fighter told by his tactics
that he is hurt enough to break off, and told by his menu that he is not
hurt enough to Recover, has been given two different readings of one
number.

AND SO DID THE BRICK'S POSTURE. `tactics/catalog/stand_and_take_it.py`
kept a fifth copy --- its own `_STUN_HEALTHY_PCT = 50` and its own
`current_body <= 0` test --- which is exactly `classify_health(...) ==
"healthy"`, and now says so.

`stun_percent` is the sixth: two tactics recomputed the percentage for
the sentence they print, so the expression that decides and the
expression the reader is shown were separate statements of one number.
"""
from __future__ import annotations

from typing import Any, Literal

#: Below half STUN is "wounded" -- the rung the Recover offer also uses.
STUN_WOUNDED_PCT = 50
#: At or below a quarter STUN is "critical", and so is any BODY at or below
#: zero (6E1 p.421's dying is not a matter of degree).
STUN_CRITICAL_PCT = 25

HealthState = Literal["healthy", "wounded", "critical"]


def stun_percent(combatant: Any) -> int:
    """How much of his STUN this combatant has left, as a whole percent.

    THE NUMBER THE LADDER IS CUT FROM, exposed because consumers want to
    SAY it as well as branch on it: two tactics printed "Actor at N%
    STUN" in their rationale and computed N themselves, so the sentence
    the reader is shown and the rung the tactic fired on were two
    expressions that merely happened to agree.

    A combatant with no STUN maximum divides by one rather than by zero
    --- `classify_health` below never asks in that case (it answers
    "healthy" first), and a rationale that says "0% STUN" is still a
    truthful reading of a fighter who has no STUN track at all.
    """
    return round(100 * combatant.current_stun / max(combatant.max_stun, 1))


def classify_health(combatant: Any) -> HealthState:
    """Which rung of the ladder this combatant is on.

    Reads live state off the combatant (`current_stun` / `max_stun` /
    `current_body` / `max_body`), not off `combat_stats()`, because it
    changes mid-fight; both the flat and the HD-shaped participant answer
    those four names.

    A combatant with no STUN maximum at all is `"healthy"`: there is no
    ladder to place him on, and the arithmetic below would divide by zero.
    A zero `max_body` is divided as `max(max_body, 1)` for the same reason.
    Both were the existing behaviour and are pinned by tests rather than
    left to the next reader to rediscover.
    """
    if combatant.max_stun <= 0:
        return "healthy"
    stun_pct = stun_percent(combatant)
    body_pct = round(100 * combatant.current_body / max(combatant.max_body, 1))
    if body_pct <= 0 or stun_pct <= STUN_CRITICAL_PCT:
        return "critical"
    if stun_pct < STUN_WOUNDED_PCT:
        return "wounded"
    return "healthy"
