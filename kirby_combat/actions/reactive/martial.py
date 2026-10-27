"""Martial Dodge and Martial Block: what a bought maneuver adds to the plain one.

6E2 p.93: Martial Dodge and Martial Block "function identically to the
regular Combat Maneuvers of similar name, but with different modifiers to
OCV, DCV, and damage". The table on the same page prices them: Martial Dodge
DCV +5 ("Dodge, Affects All Attacks, Abort") against Dodge's +3 (6E2 p.58),
Martial Block OCV +2 / DCV +2 ("Block, Abort") against Block's +0 / +0.

So a fighter who bought one does not get a second action. He gets the plain
action at his maneuver's numbers, and this module is where those numbers are
read off his own sheet (`maneuver_view()`, HD's OCV/DCV columns, parsed by
`cv_parser`). The plain `dodge` and `block` offers, the out-of-turn Abort
(`loop/reactions.py`) and the attack door all ask here, so the three cannot
disagree about how good his Dodge is.

RULING, labelled: when a man owns more than one, the best one is used. Every
Martial Dodge and Martial Block on the 6E2 p.93 table is strictly better than
the plain maneuver, and nothing in the book makes a fighter choose a worse
defence than one he knows, so offering him the choice would only add an
option nobody should take.

WHERE THE KIRBY-API DRIVER WAS WRONG (corrected here). It folded a Martial
Block's DCV value into the BLOCK ROLL. The roll is an Attack Roll (6E2 p.59),
so it is the maneuver's OCV column that improves it; the DCV column is a DCV
bonus, and 6E2 p.59 says Block's CV bonuses "are general ones; they apply
against all characters". Both are applied, each to its own CV.

SEPARATE FROM `actions/maneuver_effects.py`, deliberately. That decoder turns
an OFFENSIVE maneuver's EFFECT into a `MartialEffect` and refuses Block and
Dodge ("defensive, not offensive"); this module reads only the OCV/DCV
columns of the two defensive ones and never parses an EFFECT string itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: 6E2 p.58, the Combat Maneuvers Table: Dodge is +3 DCV, Block +0 / +0.
PLAIN_DODGE_DCV = 3
PLAIN_BLOCK_OCV = 0
PLAIN_BLOCK_DCV = 0


@dataclass(frozen=True)
class DefensiveManeuver:
    """The numbers one defensive maneuver gives, and whose they are."""

    #: The bought maneuver's display name, or None for the plain maneuver.
    name: str | None
    ocv: int
    dcv: int


def _maneuvers(combatant: Any) -> list[Any]:
    view = getattr(combatant, "maneuver_view", None)
    if view is None:
        # A flat stat block has no martial arts to read.
        return []
    return list(view())


def dodge_maneuver(combatant: Any) -> DefensiveManeuver:
    """His best Dodge: a bought Martial Dodge if it beats +3, else the plain one."""
    best = DefensiveManeuver(name=None, ocv=0, dcv=PLAIN_DODGE_DCV)
    for mv in _maneuvers(combatant):
        if mv.is_dodge and int(mv.dcv) > best.dcv:
            best = DefensiveManeuver(name=mv.name, ocv=0, dcv=int(mv.dcv))
    return best


def block_maneuver(combatant: Any) -> DefensiveManeuver:
    """His best Block: the bought Martial Block with the best roll, else plain.

    Ranked on OCV first because the OCV is what stops the blow (the roll),
    then DCV.
    """
    best = DefensiveManeuver(name=None, ocv=PLAIN_BLOCK_OCV, dcv=PLAIN_BLOCK_DCV)
    for mv in _maneuvers(combatant):
        if not mv.is_block:
            continue
        candidate = DefensiveManeuver(name=mv.name, ocv=int(mv.ocv), dcv=int(mv.dcv))
        if (candidate.ocv, candidate.dcv) > (best.ocv, best.dcv):
            best = candidate
    return best
