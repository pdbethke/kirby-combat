"""Dice rolling protocol and default RandomRoller."""
from __future__ import annotations

import random
from typing import Protocol


class DiceRoller(Protocol):
    """Protocol for dice rolling. Engine accepts any implementation."""

    def roll_dice(self, count: int, sides: int = 6) -> list[int]:
        """Roll `count` dice with `sides` faces. Returns individual results."""
        ...

    def roll_half_die(self) -> int:
        """Roll a half-die: returns 1, 2, or 3 (representing 0, +1, 1 pip in HERO)."""
        ...


class RandomRoller:
    """Default engine roller using Python's random module."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def roll_dice(self, count: int, sides: int = 6) -> list[int]:
        # Accept whole-valued floats: dice counts computed from canon
        # HDC-imported stats arrive as floats (the cost engine's
        # characteristic_value() returns float, so e.g. PRE 15.0 // 5
        # = 3.0 dice). A NON-integral count is rejected, not truncated:
        # it would mean a half-die leaked into the d6 count, and HERO
        # half-dice must go through roll_half_die() instead.
        n = int(count)
        if n != count:
            raise ValueError(
                f"roll_dice count must be a whole number, got {count!r}; "
                "half-dice are rolled via roll_half_die()"
            )
        return [self._rng.randint(1, sides) for _ in range(n)]

    def roll_half_die(self) -> int:
        # HERO half-die: 1-2 = 0 pip, 3-4 = +1 pip, 5-6 = 1 body (caller decides semantics)
        # Implementation rolls 1d6 and maps to 1/2/3 buckets.
        raw = self._rng.randint(1, 6)
        if raw <= 2:
            return 1
        if raw <= 4:
            return 2
        return 3
