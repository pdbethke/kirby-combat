"""A chosen Presence Attack LANDS --- 6E2 p.137-139.

The resolvers rolled a Presence Attack, named its tier and wrote the tier
into an `ActionResolved` payload, and that was all. `PresenceEffects.apply`
was called from one place, `violence.py`, so a shout a fighter CHOSE to make
frightened nobody, while a blow he struck in passing frightened everyone who
saw it. The driver this engine replaced (the parked consumer's,
`_resolve_presence_attack`, deleted in 70ad60f) did apply it; the port lost
it.

This module is the one door a chosen Presence Attack goes through, single or
group, so the two cannot drift apart again:

* **Dice** (6E2 p.137): 1d6 per 5 PRE, then the Presence Attack Modifiers
  Table (6E2 p.138). "In combat -1d6" applies to every one this engine
  resolves, exactly as the driver applied it and as `violence.py` does.
  The driver's three invented bonuses (outnumbering 3:1, PRE more than 1.5x
  the target's, a recent takedown) are NOT ported: none is on p.138's
  table, and the rule here is that a rule that cannot be cited does not
  ship.
* **One roll for a group.** A group Presence Attack is one terrifying moment
  judged against each target's PRE (6E2 p.137: it "affects everyone who
  can hear the character performing it, provided it's intended for them").
* **Stunned targets are immune** (6E2 p.106), read from the fight.
* **PRE Defense** raises the PRE the roll is judged against (6E1 p.178); see
  ``pre_defense_of``.
* **The tier is applied** through `PresenceEffects.apply`, so `can_act`, the
  half/zero DCV, the hesitation and the Half-Phase limit all read it.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

#: HD's LIMITEDPOWER text for 6E1 p.178's example Presence Defense ("+20 PRE;
#: Only To Protect Against Presence Attacks (-1)"). Matching HD's rendering
#: of a Limitation, not inventing a category --- the same move as
#: `complications._INTENSITY`.
_ONLY_TO_RESIST = re.compile(r"protect\s+against\s+presence\s+attacks", re.I)


def pre_defense_of(combatant: Any) -> int:
    """PRE this combatant adds ONLY when resisting a Presence Attack.

    6E has no Presence Defense Power. 6E1 p.178 builds one as "+20 PRE; Only
    To Protect Against Presence Attacks (-1)", so the defence is PRE, and
    what this returns is the part of it that is NOT already in his combat
    PRE.

    HD records whether a purchase counts toward the character's total
    (``AFFECTS_TOTAL``), and every Presence Defense in the libraries we hold
    is written ``AFFECTS_TOTAL="Yes"`` --- it is already inside
    ``combat_stats().pre``, so it already resists, and adding it here would
    count it twice. Only a purchase HD keeps OUT of the total adds here.

    KNOWN GAP, recorded rather than hidden: `kirby_cost.io.build_json` does
    not carry a modifier's ALIAS, and LIMITEDPOWER's alias IS the limitation.
    A build that came through a build doc therefore cannot say what its PRE
    is limited to, and this reads 0 for it. Nothing in the character corpus
    owns a Presence Defense today (only the power libraries do).
    """
    hero = getattr(combatant, "hero", None)
    total = 0
    for power in (getattr(hero, "powers", None) or []):
        if (getattr(power, "xmlid", "") or "").upper() != "PRE":
            continue
        if bool(getattr(power, "affect_total", True)):
            continue
        for modifier in (getattr(power, "assigned_modifiers", None) or []):
            if ((getattr(modifier, "xmlid", "") or "").upper() == "LIMITEDPOWER"
                    and _ONLY_TO_RESIST.search(getattr(modifier, "alias", "") or "")):
                total += int(getattr(power, "levels", 0) or 0)
                break
    return total


def presence_dice(actor: Any) -> int:
    """How many dice a Presence Attack in a fight rolls (6E2 p.137-138)."""
    from kirby_combat.pre_attacks.presence import (
        IN_COMBAT_DICE_MODIFIER, base_pre_dice,
    )

    return max(0, base_pre_dice(actor) + IN_COMBAT_DICE_MODIFIER)


def roll_presence_attack(
    session: "CombatSession", actor: Any, targets: list, roller,
) -> dict[str, Any]:
    """Roll ONE Presence Attack against ``targets``: target id -> result.

    Pure apart from the dice: it reads the fight (who is Stunned) and writes
    nothing, so the caller can log the declaration BEFORE the effects it
    caused, which is the order a replay reads them in.
    """
    from kirby_combat.pre_attacks.presence import (
        IN_COMBAT_DICE_MODIFIER, resolve_presence_attack,
    )
    from kirby_combat.statuses import stunned_or_recovering_for

    dice_values = roller.roll_dice(presence_dice(actor))
    return {
        target.id: resolve_presence_attack(
            actor, target, dice_values,
            bonus_dice_from_situation=IN_COMBAT_DICE_MODIFIER,
            target_pre_defense=pre_defense_of(target),
            target_stunned=stunned_or_recovering_for(session, target.id),
        )
        for target in targets
    }


def apply_presence_results(
    session: "CombatSession", actor_id: str, results: dict[str, Any],
) -> "CombatSession":
    """Record every landed tier (`PresenceApplied`), in target order."""
    from kirby_combat.pre_attacks.presence_effects import PresenceEffects

    for target_id, result in results.items():
        session, _ = PresenceEffects.apply(
            session, target_id=target_id, attacker_id=actor_id,
            tier=result.effect,
        )
    return session


def payload_for(result) -> dict[str, Any]:
    """What one target's result says in the log."""
    return {
        "effect": result.effect,
        "roll_total": result.roll_total,
        "dice": result.effective_dice,
        "target_pre": result.target_pre,
        "resisting_pre": result.resisting_pre,
        "audit": list(result.audit),
    }
