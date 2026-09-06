"""Climbing — status tokens, rates and combat modifiers (6E1 p70, 6E2 p48-49).

Kept in its own module rather than added to llm_driver.py because it is pure:
no DB, no session, no dice. That makes the rulebook numbers testable on their
own, which matters here because two rulebook passages disagree (see below).
"""
from __future__ import annotations

from dataclasses import dataclass

# 6E1 p70: base climbing speed is 2m per Phase (at most). The optional rule
# allows +2m per -3 to the roll; the GM may cap how far that goes, and this
# codebase caps it at one step.
CLIMB_BASE_M: float = 2.0
CLIMB_FAST_M: float = 4.0
CLIMB_FAST_PENALTY: int = -3

CLIMB_STATUS_PREFIX = "climbing:"


def climb_status(wall_id: str) -> str:
    """The status token naming the face a character is currently on."""
    return f"{CLIMB_STATUS_PREFIX}{wall_id}"


def climbing_wall_id(statuses: set[str]) -> str | None:
    """The wall id a character is climbing, or None if they are not."""
    for s in statuses or ():
        if s.startswith(CLIMB_STATUS_PREFIX):
            return s[len(CLIMB_STATUS_PREFIX):]
    return None


def is_climbing(statuses: set[str]) -> bool:
    return climbing_wall_id(statuses) is not None


@dataclass(frozen=True)
class ClimbModifiers:
    """Combat penalties while climbing, per 6E2 p48-49.

    NOTE the rulebook disagrees with itself. 6E1 p70 summarises this as "a
    climbing character's OCV and DCV are halved". The detailed treatment it
    explicitly defers to (6E2 p48-49) says something different and more
    specific: DCV only, no OCV penalty, plus a -2 DC penalty 6E1 omits. This
    implements 6E2. Do not "fix" it back to 6E1 without a ruling.
    """
    dcv_multiplier: float
    dcv_delta: int
    dc_penalty: int


def climb_modifiers(climb_difficulty: int) -> ClimbModifiers:
    """Modifiers for a face of the given difficulty (6E2 p48-49).

    Ordinary (0): -1 DCV, no OCV penalty, no DC penalty.
    Difficult (> 0): DCV reduced by up to half, and -2 DCs from all attacks.
    """
    if climb_difficulty <= 0:
        return ClimbModifiers(dcv_multiplier=1.0, dcv_delta=-1, dc_penalty=0)
    return ClimbModifiers(dcv_multiplier=0.5, dcv_delta=0, dc_penalty=-2)
