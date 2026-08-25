"""Mental Blast — damage vs Mental Defense, no BODY/KB.

6E1 pg 105: Mental Blast deals STUN-only damage. STUN is reduced by the
target's Mental Defense (MD). No BODY damage. No knockback. Stunning rules
apply normally (STUN dealt > CON -> Stunned).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.models import Combatant


@dataclass
class MentalBlastResult:
    target_id: str
    raw_stun: int                # rolled total before MD
    stun_dealt: int              # raw_stun - md, floored at 0
    body_dealt: int              # always 0
    knockback_m: float           # always 0.0
    target_stunned: bool
    target_ko: bool              # current_stun went to 0 or below
    audit: list[str] = field(default_factory=list)


def resolve_mental_blast(
    attacker: Combatant,
    target: Combatant,
    damage_dice_values: list[int],
) -> MentalBlastResult:
    if not attacker.is_mentalist:
        raise ValueError(
            f"Combatant {attacker.id} is not marked as mentalist; cannot use Mental Blast"
        )
    raw_stun = sum(damage_dice_values)
    stun_dealt = max(0, raw_stun - target.md)
    body_dealt = 0

    new_current_stun = target.current_stun - stun_dealt
    # Raw int in hand: this is the PROJECTED post-damage STUN, not yet
    # written back onto `target.state`, so there is no participant object
    # to read `.is_ko` from here. The rule itself is defined once, on
    # kirby_combat.participant.Stunnable.is_ko.
    target_ko = new_current_stun <= 0
    target_stunned = stun_dealt > target.con

    audit = [
        f"Mental Blast: raw_stun={raw_stun} - MD={target.md} = {stun_dealt} STUN",
        f"BODY=0; KB=0 (mental attacks deal STUN only, 6E1 p105)",
        f"Stunned={target_stunned} (STUN > CON {target.con}); KO={target_ko}",
    ]
    return MentalBlastResult(
        target_id=target.id, raw_stun=raw_stun,
        stun_dealt=stun_dealt, body_dealt=body_dealt, knockback_m=0.0,
        target_stunned=target_stunned, target_ko=target_ko,
        audit=audit,
    )
