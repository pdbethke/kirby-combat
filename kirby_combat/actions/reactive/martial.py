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
    #: A Block that also takes hold of the attacker ("Grab One Limb, Block",
    #: Grappling Block) or puts him down ("Block, Target Falls", Defensive
    #: Throw) when it succeeds. False for a Dodge and the plain Block.
    grabs: bool
    throws: bool


def _maneuvers(combatant: Any) -> list[Any]:
    view = getattr(combatant, "maneuver_view", None)
    if view is None:
        # A flat stat block has no martial arts to read.
        return []
    return list(view())


def dodge_maneuver(combatant: Any) -> DefensiveManeuver:
    """His best Dodge: a bought Martial Dodge if it beats +3, else the plain one."""
    best = DefensiveManeuver(name=None, ocv=0, dcv=PLAIN_DODGE_DCV,
                             grabs=False, throws=False)
    for mv in _maneuvers(combatant):
        if mv.is_dodge and int(mv.dcv) > best.dcv:
            best = DefensiveManeuver(name=mv.name, ocv=0, dcv=int(mv.dcv),
                                     grabs=False, throws=False)
    return best


def _block_riders(mv: Any) -> tuple[bool, bool]:
    """What a bought Block does besides blocking: (takes hold, throws down).

    HD's builder (HERO System Martial Arts elements) adds them to the Block:
    Grappling Block "Grab One Limb, Block", Defensive Throw "Block, Target
    Falls". The mechanics are 6E core: a Grab (6E2 p.67) and a fall (6E2
    p.94's Target Falls). RULING: the successful Block roll is the roll that
    takes hold or throws --- the maneuver makes no other.

    Anything else beside the Block --- Root's "[STRDC] to resist Shove" ---
    is not read; the Block still blocks at its numbers.
    """
    import re

    effect = (getattr(mv, "effect", "") or "").lower()
    residue = re.sub(r"\bblock\b|\babort\b|\bgrab one limb\b|\btarget falls\b",
                     " ", effect)
    if re.sub(r"[\s;,]+", "", residue):
        return False, False
    return (bool(re.search(r"\bgrab one limb\b", effect)),
            bool(re.search(r"\btarget falls\b", effect)))


def block_maneuver(combatant: Any) -> DefensiveManeuver:
    """His best Block: the bought Martial Block with the best roll, else plain.

    Ranked on OCV first because the OCV is what stops the blow (the roll),
    then DCV.
    """
    best = DefensiveManeuver(name=None, ocv=PLAIN_BLOCK_OCV, dcv=PLAIN_BLOCK_DCV,
                             grabs=False, throws=False)
    for mv in _maneuvers(combatant):
        if not mv.is_block:
            continue
        grabs, throws = _block_riders(mv)
        candidate = DefensiveManeuver(name=mv.name, ocv=int(mv.ocv), dcv=int(mv.dcv),
                                      grabs=grabs, throws=throws)
        if (candidate.ocv, candidate.dcv) > (best.ocv, best.dcv):
            best = candidate
    return best


# ---------------------------------------------------------------------------
# Martial Escape (6E2 p.94)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EscapeManeuver:
    """What a bought escape maneuver adds to breaking a Grab."""

    name: str
    #: STR added to his own when he rolls to break out.
    str_bonus: int
    #: A custom "[DAMAGE] vs Grabs, Target Falls": the grabber goes down
    #: when the escape succeeds.
    grabber_falls: bool


def _decode_escape(mv: Any) -> EscapeManeuver | None:
    """A Martial Escape's bonus, or None for anything else.

    6E2 p.94: "The character adds the STR from this maneuver to his own STR
    when rolling BODY to break out from a Grab; the additional STR has no
    other effect." HD writes it "[STRDC] vs. Grabs" (Main6E.hdt), at +5 STR a
    DC (6E2 p.94: "+5 STR to any Maneuver that grants extra STR for limited
    purposes"); a custom one writes "[DAMAGE]" with damage type STR.

    STRICT, like the offensive decoder: an element this does not know ---
    Reversal's "Grab Two Limbs" after the escape --- means it is not read.
    """
    import re

    from kirby_combat.actions.maneuver_effects import ManeuverDamage

    effect = (getattr(mv, "effect", "") or "").lower()
    if not re.search(r"\bvs\.? grabs\b", effect):
        return None
    residue = re.sub(r"\bvs\.? grabs\b|\[(strdc|damage)\]|\btarget falls\b", " ", effect)
    if re.sub(r"[\s;,]+", "", residue):
        return None
    if ManeuverDamage(mv.damage_type) is not ManeuverDamage.STR or not mv.add_str:
        return None
    return EscapeManeuver(
        name=mv.name, str_bonus=5 * int(mv.dc_bonus),
        grabber_falls=bool(re.search(r"\btarget falls\b", effect)),
    )


def escape_maneuver(combatant: Any) -> EscapeManeuver | None:
    """His best Martial Escape, or None. RULING, as for Dodge and Block above:
    the best one, because nothing makes a man break out weaker than he can."""
    best: EscapeManeuver | None = None
    for mv in _maneuvers(combatant):
        found = _decode_escape(mv)
        if found is not None and (best is None or (found.str_bonus, found.grabber_falls)
                                  > (best.str_bonus, best.grabber_falls)):
            best = found
    return best
