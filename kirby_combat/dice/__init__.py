"""Dice rolling: engine rolls by default, tests inject FakeRoller."""
from kirby_combat.dice.roller import DiceRoller, RandomRoller
from kirby_combat.dice.fake import FakeRoller

__all__ = ["DiceRoller", "RandomRoller", "FakeRoller"]
