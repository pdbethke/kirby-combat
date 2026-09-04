"""Deterministic roller for tests. Yields pre-computed dice results."""
from __future__ import annotations


class FakeRoller:
    """Yields pre-computed dice values for deterministic tests.

    Usage::

        f = FakeRoller([[3, 4, 5], [1, 2, 3]])
        f.roll_dice(3, sides=6)   # -> [3, 4, 5]
        f.roll_dice(3, sides=6)   # -> [1, 2, 3]

    A half die needs no special fixture: append one more value to the batch
    that carries it, because `resolution.damage` reads the last value of
    `dice.damage` as the half-die raw roll.
    """

    def __init__(self, dice_results: list[list[int]]) -> None:
        self._dice = [list(inner) for inner in dice_results]
        self._dice_idx = 0

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
