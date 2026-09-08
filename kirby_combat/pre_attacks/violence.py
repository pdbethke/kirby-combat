"""A violent act is a Presence Attack --- 6E2 p.138's modifiers table.

The engine could always RESOLVE a Presence Attack and always knew what
the tiers do to a man. What it could not do was notice one happening.
Only a declared `presence_attack` action produced one, so a fighter could
tear somebody in half in front of six onlookers and none of them so much
as blinked.

At the O.K. Corral that showed as seven armed men emptying revolvers into
Power Lad's hide for twenty-eight Phases, achieving nothing and never
once wavering. Brave in a way nobody is brave.

The table (6E2 p.138) prices it directly:

    Violent action              +1d6
    Extremely violent action    +2d6
    Incredibly violent action   +3d6

THE THREE RUNGS ARE THE BOOK'S. WHICH BLOW SITS ON WHICH IS OURS, and
the book is explicit that it is the GM's call --- it names them and gives
no numbers. This grades by what the damage did to the man who took it,
because that is what the onlookers saw. A blow that puts somebody on the
ground dying is not the same event as one that opens his sleeve, and
"how bad did that look" tracks what it did to him rather than how big the
attacker's dice are. A `Basis` of judgement, quotable in an audit trail.
"""
from __future__ import annotations

#: 6E2 p.138, the three named rungs. Nothing invents a fourth.
VIOLENT = 1
EXTREMELY_VIOLENT = 2
INCREDIBLY_VIOLENT = 3

#: The judgement, stated as a number so it can be argued with: a single
#: blow taking half of a man's BODY is "extremely violent". Below that,
#: blood was drawn and no more.
MAIMING_FRACTION = 0.5

#: Why each rung was chosen, for the audit trail.
REASONS = {
    INCREDIBLY_VIOLENT: "the blow left the target dying or dead (6E2 p.138, "
                        "'incredibly violent action')",
    EXTREMELY_VIOLENT: "the blow took half or more of the target's BODY in "
                       "one hit (6E2 p.138, 'extremely violent action')",
    VIOLENT: "the blow drew blood (6E2 p.138, 'violent action')",
    0: "no BODY got through; nothing anybody saw was frightening",
}


def violence_bonus_dice(*, body_dealt: float, target_max_body: float,
                        target_body_after: float) -> int:
    """Bonus Presence dice for how the blow LOOKED, 0 to 3.

    Zero when no BODY got through, which is the case that matters most
    for reading a fight honestly: a revolver emptied into something it
    cannot hurt is loud and not frightening, and grading by the
    attacker's dice rather than by the wound would have called it terror.
    """
    if body_dealt <= 0:
        return 0
    if target_body_after <= 0:
        return INCREDIBLY_VIOLENT
    if target_max_body > 0 and body_dealt >= target_max_body * MAIMING_FRACTION:
        return EXTREMELY_VIOLENT
    return VIOLENT


def reason_for(bonus: int) -> str:
    """The audit line for a bonus, so a fight can be read back."""
    return REASONS.get(bonus, REASONS[0])


class _Speaker:
    """The two fields `resolve_presence_attack` reads off a combatant."""

    __slots__ = ("id", "pre")

    def __init__(self, id: str, pre: int) -> None:
        self.id = id
        self.pre = int(pre or 0)


#: 6E2 p.139's ladder, weakest first. `one_level_lighter` walks it.
#:
#: `overwhelmed` BELONGS HERE and leaving it out was a real bug, caught by
#: the first test that resolved a big Presence Attack rather than reasoning
#: about one: PRE 40 plus an incredibly violent action rolls sixty against
#: a gunman's PRE 15, which is `overwhelmed` -- and a ladder that stopped
#: at `cowed` stepped the STRONGEST possible result down to nothing at all.
#: The most frightening thing in the fight frightened nobody.
_LADDER = ("no_effect", "impressed", "very_impressed", "awed", "cowed",
           "overwhelmed")


def one_level_lighter(tier: str) -> str:
    """One rung down 6E2 p.139's ladder.

    6E2 p.137: "the effects of a Presence Attack are reduced by one level
    when applied to anyone against whom the attack isn't specifically
    directed." Nobody swung at the onlookers --- the blow was aimed at the
    man it killed --- so what they take is a level lighter than what a
    Presence Attack thrown AT them would have been.

    """
    try:
        index = _LADDER.index(tier)
    except ValueError:
        return "no_effect"
    return _LADDER[max(0, index - 1)]


def presence_from_violence(
    session,
    *,
    attacker,
    target_id: str,
    body_dealt: float,
    target_max_body: float,
    target_body_after: float,
    roller,
):
    """Fire the Presence Attack a violent blow makes, at everyone who saw it.

    Returns the session UNCHANGED when nothing frightening happened, which
    is the common case and the one that keeps ordinary fights ordinary: a
    blow that got no BODY through is loud and not frightening.

    The victim is not an onlooker --- what is happening to him is not a
    thing he is watching happen to somebody else --- and neither is the
    attacker.

    WITNESSES ARE EVERY OTHER COMBATANT, which is a simplification and
    should be said out loud: 6E2 p.137 makes a Presence Attack land on
    "everyone who can hear the character performing it", and this engine
    has a perception layer that could answer that properly. Gating on it
    is the right follow-up; assuming a 5.5m lot is within earshot is fine
    for now and wrong in a warehouse.
    """
    from kirby_combat.pre_attacks.presence import (
        IN_COMBAT_DICE_MODIFIER, resolve_presence_attack,
    )
    from kirby_combat.pre_attacks.presence_effects import PresenceEffects

    bonus = violence_bonus_dice(
        body_dealt=body_dealt, target_max_body=target_max_body,
        target_body_after=target_body_after,
    )
    if not bonus:
        return session

    attacker_id = getattr(attacker, "id", "")
    situation_dice = bonus + IN_COMBAT_DICE_MODIFIER

    for witness in list(session.combatants.values()):
        witness_id = getattr(witness, "id", "")
        if witness_id in (attacker_id, target_id):
            continue
        # `resolve_presence_attack` wants combatants -- it reads `.pre`
        # AND `.id` for the record it returns -- while a HeroCombatant keeps
        # PRE behind `combat_stats()`. `_Speaker` is the two fields it
        # actually uses, rather than teaching that resolver a second shape.
        speaker = _Speaker(attacker_id, attacker.combat_stats().pre)
        listener = _Speaker(witness_id, witness.combat_stats().pre)
        dice = max(0, speaker.pre // 5 + situation_dice)
        result = resolve_presence_attack(
            speaker, listener, roller.roll_dice(dice),
            bonus_dice_from_situation=situation_dice,
        )
        session, _ = PresenceEffects.apply(
            session, target_id=witness_id, attacker_id=attacker_id,
            tier=one_level_lighter(result.effect),
        )
    return session
