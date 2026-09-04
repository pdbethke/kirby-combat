"""Dice rolling protocol and default RandomRoller.

Based in part on the work of Bill Bame — see this package's ``__init__``
for the attribution note.
"""
from __future__ import annotations

import random
import secrets
from typing import Protocol


class DiceRoller(Protocol):
    """Protocol for dice rolling. Engine accepts any implementation."""

    def roll_dice(self, count: int, sides: int = 6) -> list[int]:
        """Roll `count` dice with `sides` faces. Returns individual results."""
        ...


class RandomRoller:
    """Default engine roller using Python's random module.

    Always seeded with a REAL number, and always able to hand that number
    back. An unseeded ``random.Random()`` draws from OS entropy, which means
    the seed never exists as a value and a fight can never be replayed once
    it has been fought. Choosing the seed explicitly costs nothing and makes
    every sequence reproducible: record ``roller.seed`` alongside the fight,
    and ``RandomRoller(seed=<recorded>)`` rolls it again, die for die.

    That is the difference between asserting the dice were fair and proving
    it. See ``tests/test_dice_fairness.py``.
    """

    def __init__(self, seed: int | None = None) -> None:
        # secrets, not random: the default seed should be as unguessable as
        # the OS entropy it replaces. Being recordable must not make it
        # predictable to a player who would rather know the next roll.
        self._seed = secrets.randbits(64) if seed is None else seed
        self._rng = random.Random(self._seed)

    @property
    def seed(self) -> int:
        """The seed this roller rolls from. Never None -- see the class doc."""
        return self._seed

    def roll_dice(self, count: int, sides: int = 6) -> list[int]:
        # Accept whole-valued floats: dice counts computed from canon
        # HDC-imported stats arrive as floats (the cost engine's
        # characteristic_value() returns float, so e.g. PRE 15.0 // 5
        # = 3.0 dice). A NON-integral count is rejected, not truncated:
        # truncating would silently DROP a half die.
        #
        # A half die is not rolled by a separate call. The caller asks for
        # one extra whole d6 and `resolution.damage` reads the LAST value of
        # the batch as the half-die raw roll, converting it there. Keep that
        # one conversion; a second one here is how the two drift apart.
        n = int(count)
        if n != count:
            raise ValueError(
                f"roll_dice count must be a whole number, got {count!r}; "
                "a half die is an extra whole d6, converted in resolution.damage"
            )
        return [self._rng.randint(1, sides) for _ in range(n)]
