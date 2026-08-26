"""How a campaign settles two combatants acting on the same DEX.

6E2 p.21 gives a default and an explicit alternative:

    "the GM should resolve the situation by having both characters make
    DEX Rolls ... The character who succeeds with his DEX Roll by the most
    gets to act first"

    "Alternately, the GM may dispense with the DEX Roll ... the character
    with the highest INT acts first (if their INTs are also tied, use PRE)"

RANDOM is not from the books; it is the campaign option the engine already
declared as `template.randomize_dex_ties` and never wired up.
"""
from __future__ import annotations

from enum import Enum

from kirby_cost.engine.rolls import characteristic_roll


class TieRule(Enum):
    """A campaign's chosen method for breaking a DEX tie in acting order."""

    #: 6E2 p.21 default: both combatants roll a DEX Roll; whoever succeeds
    #: by the most acts first.
    DEX_ROLL = "dex_roll"

    #: 6E2 p.21's stated alternative: highest INT acts first, PRE as the
    #: fallback when INT also ties.
    INT_THEN_PRE = "int_then_pre"

    #: Not from the books. The campaign option the engine already declared
    #: as `template.randomize_dex_ties` and never wired up: re-roll on a d6.
    RANDOM = "random"


def dex_roll_target(dex: int) -> int:
    """The 3d6 target for a contested DEX Roll (6E2 p.21), given PRINTED DEX.

    Callers MUST pass printed DEX (`stats.dex`), never any effective/boosted
    DEX. 6E1 p.116 is explicit that a power like Lightning Reflexes which
    lets a character act sooner does not touch his Skill Rolls: "his
    Agility Skill Rolls remain 12-". Lightning Reflexes' effective-DEX boost
    applies to acting order only -- this function must never be handed
    that boosted value, so it takes the plain characteristic as a
    bare int (not a combatant, so there is nothing to read the wrong field
    off of) and this is the single named home for that contract.

    Delegates the 9 + DEX/5 math to kirby_cost.engine.rolls.characteristic_roll,
    which rounds (DEX 13 -> 12-); a local `9 + DEX // 5` truncates and
    disagrees with the canon on 16 of 40 characteristic values.
    """
    return characteristic_roll(dex)
