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

AND ENUMERATION HOLDS THE FOURTH STATEMENT OF IT. `enumerate_actions`
offers a Recover "when the actor is wounded (<½ STUN)" (see its docstring,
`kirby_combat/enumeration.py`). That is the same rung as `"wounded"` here,
and it must stay the same rung: a fighter told by his tactics that he is
hurt enough to break off, and told by his menu that he is not hurt enough
to Recover, has been given two different readings of one number.
"""
from __future__ import annotations

from typing import Any, Literal

#: Below half STUN is "wounded" -- the rung the Recover offer also uses.
STUN_WOUNDED_PCT = 50
#: At or below a quarter STUN is "critical", and so is any BODY at or below
#: zero (6E1 p.421's dying is not a matter of degree).
STUN_CRITICAL_PCT = 25

HealthState = Literal["healthy", "wounded", "critical"]


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
    max_stun = combatant.max_stun
    if max_stun <= 0:
        return "healthy"
    stun_pct = round(100 * combatant.current_stun / max_stun)
    body_pct = round(100 * combatant.current_body / max(combatant.max_body, 1))
    if body_pct <= 0 or stun_pct <= STUN_CRITICAL_PCT:
        return "critical"
    if stun_pct < STUN_WOUNDED_PCT:
        return "wounded"
    return "healthy"
