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
* **A repeat is worth a die less** (6E2 p.140): "Each time a character
  repeats a Presence Attack, he gets -1d6 of effect (-1d6 on the second
  attack, -2d6 on the third attack, and so forth)", against "the same
  targets". Counted per target from the fight's own log
  (``repeats_against``), so one group roll is judged on each man's own
  dice. Only CHOSEN Presence Attacks count: the one a violent blow makes
  (``violence.py``) is the blow's, not a shout he repeated. The count is
  never reset --- the page gives no recovery, and a fight is short.
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


def repeats_against(session: "CombatSession", attacker_id: str,
                    target_id: str) -> int:
    """How many Presence Attacks ``attacker_id`` has already made at
    ``target_id`` in this fight --- single or group (6E2 p.140).

    Read off the resolutions (the group declaration names no targets; its
    payload names every one).
    """
    from kirby_combat.pre_attacks.in_the_phase import PRESENCE_KINDS

    count = 0
    for evt in session.event_log:
        if getattr(evt, "kind", None) != "ActionResolved":
            continue
        author = getattr(evt, "author", None)
        if getattr(author, "id", None) != attacker_id:
            continue
        payload = getattr(evt, "result_payload", None) or {}
        kind = payload.get("kind")
        if kind not in PRESENCE_KINDS:
            continue
        if payload.get("target_id") == target_id or target_id in (
                payload.get("targets") or {}):
            count += 1
    return count


def presence_dice(actor: Any, *, repeats: int) -> int:
    """How many dice a Presence Attack in a fight rolls (6E2 p.137-138),
    after ``repeats`` earlier ones at the same target (6E2 p.140)."""
    from kirby_combat.pre_attacks.presence import (
        IN_COMBAT_DICE_MODIFIER, base_pre_dice,
    )

    return max(0, base_pre_dice(actor) + IN_COMBAT_DICE_MODIFIER - int(repeats))


def without_spent_shouts(session: "CombatSession", actor: Any,
                         menu: list, enemies: list) -> list:
    """The menu less every Presence Attack that would roll no dice.

    A 0d6 Presence Attack totals 0 and can never reach a target's PRE (6E2
    p.139), so it is a free action that buys nothing --- one a chooser can
    take in every Phase without end. A group offer stays while any target
    would still face a die.
    """
    from kirby_combat.pre_attacks.in_the_phase import PRESENCE_KINDS

    def dice_at(target_id: str) -> int:
        return presence_dice(
            actor, repeats=repeats_against(session, actor.id, target_id))

    kept = []
    for offer in menu:
        if offer.kind not in PRESENCE_KINDS:
            kept.append(offer)
        elif offer.kind == "presence_attack":
            if offer.target_id and dice_at(offer.target_id) > 0:
                kept.append(offer)
        elif any(dice_at(e.id) > 0 for e in enemies):
            kept.append(offer)
    return kept


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

    # ONE ROLL, JUDGED ON EACH MAN'S OWN DICE. A repeat costs a die against
    # the man who has heard it before (6E2 p.140) and not against one who
    # has not, so the roll is made at the most dice any target faces and
    # each target is judged on the first `dice` of it.
    repeats = {t.id: repeats_against(session, actor.id, t.id) for t in targets}
    dice_values = roller.roll_dice(
        max((presence_dice(actor, repeats=n) for n in repeats.values()),
            default=0))
    results = {}
    for target in targets:
        result = resolve_presence_attack(
            actor, target, dice_values,
            bonus_dice_from_situation=IN_COMBAT_DICE_MODIFIER - repeats[target.id],
            target_pre_defense=pre_defense_of(target),
            target_stunned=stunned_or_recovering_for(session, target.id),
        )
        if repeats[target.id]:
            result.audit.insert(1, (
                f"Repeated Presence Attack at this target "
                f"(#{repeats[target.id] + 1}): -{repeats[target.id]}d6 "
                f"(6E2 p.140), within the situational dice above"))
        results[target.id] = result
    return results


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
