"""Dice rolling: engine rolls by default, tests inject FakeRoller.

**Attribution.** This dice roller is based in part on the work of Bill Bame,
shared informally and with thanks. No licence condition attaches to it; the
credit is here because it is owed and because it was missing from this package
until 2026-08-28.
"""
from kirby_combat.dice.roller import DiceRoller, RandomRoller
from kirby_combat.dice.fake import FakeRoller

__all__ = ["DiceRoller", "RandomRoller", "FakeRoller"]
