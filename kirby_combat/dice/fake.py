"""Deterministic roller for tests. Yields pre-computed dice results."""
from __future__ import annotations


class FakeRoller:
    """Yields pre-computed dice values for deterministic tests.

    Usage::

        f = FakeRoller([[3, 4, 5], [1, 2, 3]], half_die_results=[2])
        f.roll_dice(3, sides=6)   # -> [3, 4, 5]
        f.roll_dice(3, sides=6)   # -> [1, 2, 3]
        f.roll_half_die()         # -> 2
    """

    def __init__(
        self,
        dice_results: list[list[int]],
        half_die_results: list[int] | None = None,
    ) -> None:
        self._dice = list(dice_results)
        self._half = list(half_die_results or [])
        self._dice_idx = 0
        self._half_idx = 0

    def roll_dice(self, count: int, sides: int = 6) -> list[int]:
        if self._dice_idx >= len(self._dice):
            raise IndexError("FakeRoller dice pool exhausted")
        result = self._dice[self._dice_idx]
        self._dice_idx += 1
        if len(result) != count:
            raise ValueError(
                f"FakeRoller: caller asked for {count} dice, fixture has {len(result)}"
            )
        return list(result)

    def roll_half_die(self) -> int:
        if self._half_idx >= len(self._half):
            raise IndexError("FakeRoller half-die pool exhausted")
        result = self._half[self._half_idx]
        self._half_idx += 1
        return result
