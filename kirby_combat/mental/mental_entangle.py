"""Mental Entangle --- 6E1 p.219's MENTAL PARALYSIS, a real Entangle.

"Characters can use Entangle to create a type of power called Mental
Paralysis. Mental Paralysis Entangles must be built with these Advantages:
ACV (uses OMCV against DMCV; +1/4), Takes No Damage From Attacks (+3/4, see
text); and Works Against EGO, Not STR (+1/4)" (6E1 p.219). The corpus marks
it with the VERSUSEGO modifier, which is what enumeration keys on.

So it is applied and escaped through the physical Entangle's own machinery
(`actions/entangle.py`: the hold, the escape ladder, DCV 0, the breakout
margin) with p.219's differences:

* **BODY** is the Entangle's: "he rolls his Entangle dice and counts the
  Normal Damage BODY" (p.217). Mental Defense takes NOTHING off it: "Mental
  Defense neither adds to the character's EGO for purposes of breaking out
  of, nor offers any other protection against, Mental Paralysis" (p.219).
  (This module used to subtract the target's MD from the dice's pip total,
  wrong twice over.)
* **Defense**: "A Mental Paralysis has Resistant Mental Defense instead of
  PD/ED." RULING: one point per die, the 1 PD/1 ED per 1d6 an Entangle has
  (p.217) carried over to the defense that replaces them; extra defense
  bought on the power is not read.
* **Escape** with EGO, 1d6 per 5 points (`actions.entangle.ego_escape_dice`),
  against that Mental Defense; or with a Mental Blast, whose STUN-only dice
  count their "BODY" as Normal Damage (p.219). Physical attacks cannot
  damage it, and Teleporting out leaves him still paralysed (p.219).

NOT BUILT (surfaced, not invented): an outside character attacking the
paralysis (it has DMCV 3 for that, p.219), its Mental Defense also protecting
the victim from other mental attacks (p.219), Pushing EGO, and the END a
breakout costs.
"""
from __future__ import annotations

from dataclasses import dataclass

from kirby_combat.actions.entangle import counted_body
from kirby_combat.models import StatBlockCombatant


@dataclass(frozen=True)
class MentalParalysisResult:
    """What a Mental Paralysis Effect Roll made: the Entangle to apply."""
    target_id: str
    body: int                    # counted Normal Damage BODY (6E1 p.217)
    md: int                      # its Resistant Mental Defense (6E1 p.219)
    audit: list[str]


def roll_mental_paralysis(
    attacker: StatBlockCombatant,
    target: StatBlockCombatant,
    body_dice_values: list[int],
) -> MentalParalysisResult:
    if not attacker.is_mentalist:
        raise ValueError(
            f"Combatant {attacker.id} is not marked as mentalist; cannot use Mental Entangle"
        )
    body = counted_body(body_dice_values)
    md = len(body_dice_values)
    return MentalParalysisResult(
        target_id=target.id, body=body, md=md,
        audit=[f"Mental Paralysis: {len(body_dice_values)}d6 -> {body} BODY "
               f"(Normal Damage count, 6E1 p.217), Mental Defense {md}; the "
               f"target's own MD {target.md} does not apply (6E1 p.219)"],
    )
