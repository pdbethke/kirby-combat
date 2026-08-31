"""The reach rule — may this hand-to-hand attack happen at all?

6E2 p56 defines Hand-To-Hand Combat as combat between characters close
enough to be within one another's Reach, with a character's base Reach set
at 1 metre around himself. 6E2 p36 states the same boundary from the other
side: combat between characters who are not within Reach is Ranged Combat
instead. 6E2 p40's Range Modifier table gives the reach band its own row,
distinct from the next band up.

This module applies that rule to a distance. It does NOT decide what a
character's Reach is — that is `hero_view._base_reach_m` (1m base plus 1m per
level of Stretching), and it is passed in.

Why a verdict rather than a bool: a gate that returns False and nothing else
cannot explain itself, and an unexplained no-op is exactly how the missing
version of this rule stayed hidden — a martial throw resolved between two
combatants six metres apart vertically, and no log line said why the close had
failed. `shortfall_m` gives the caller "1.4m short of reach" to write down.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Tolerance for float noise in computed landing positions. A target at
#: reach_m is in reach; one a fraction of a micrometre beyond it still is.
_EPS_M: float = 1e-9


@dataclass(frozen=True)
class ReachVerdict:
    """Whether a HTH attack may resolve, and by how much it misses if not."""

    in_reach: bool
    distance_m: float
    reach_m: float
    shortfall_m: float


def within_reach(distance_m: float, reach_m: float) -> ReachVerdict:
    """Apply 6E2 p56 to a measured distance.

    `distance_m` is the attacker-to-target distance at the moment the attack
    would resolve — AFTER any close, never the distance the action was chosen
    at. `reach_m` is the attacker's effective reach.
    """
    d = float(distance_m)
    r = float(reach_m)
    ok = d <= r + _EPS_M
    return ReachVerdict(
        in_reach=ok,
        distance_m=d,
        reach_m=r,
        shortfall_m=0.0 if ok else d - r,
    )
