"""What a wound does to a man: the lethality options a Gritty campaign turns on.

Western Hero's Gritty Campaign (book p.168) turns on every optional rule
that makes a gunshot dangerous. This module is the door for the ones that
follow from BODY taken, called by `recording.resolve_attack_in_session`
right after `impact.after_the_blow` and before the row, so the row can say
what the wound did.

**WOUNDING (6E2 p.110, `CombatTemplate.use_wounding`).** "A character who
takes BODY damage for any reason must make an EGO Roll at -1 for every full
2 BODY the character has taken. ... If the roll fails, the character can't
take any offensive action in his next Phase - he can't shoot, strike back,
or use any offensive Combat Maneuver. He may still move to Behind Cover,
Dodge, or use any other neutral or defensive Combat Maneuver."

  * RULING (Peter, 2026-11-27): the BODY is THIS hit's, not the running
    total.
  * A 3 always makes a Characteristic Roll and an 18 always fails it
    (6E1 p.57).
  * The flinch is read back off the log: a failed roll on a row, and no
    `PhaseSpent` of his since. Recorded rather than held, so a replay
    lands on the same menu.
  * WHAT IS OFFENSIVE is decided by an allow-list of what is not
    (`NON_OFFENSIVE_KINDS`), so an offer kind this module has never heard
    of is withheld rather than let through. Set and Hold are left out:
    Set is aiming and a Held Action waits to attack, and both are the
    offence the page takes away.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

#: 6E2 p.110: -1 "for every full 2 BODY".
BODY_PER_POINT = 2

#: 6E1 p.57.
ALWAYS_MAKES, ALWAYS_FAILS = 3, 18

#: Neutral or defensive: what a flinching man may still do (6E2 p.110
#: names moving to cover and Dodge; "any other neutral or defensive Combat
#: Maneuver"). Movement, getting up, recovering, tending the dying and
#: getting out of a hold are neither offence nor attack.
NON_OFFENSIVE_KINDS = frozenset({
    "dodge", "block", "hide", "disengage", "move_to_cover", "reposition",
    "move", "half_move", "climb", "stand_up", "recover", "stabilize",
    "pickup", "pick_up_weapon", "no_abort",
    "escape_str", "escape_ego", "escape_teleport",
})

#: The row key the check is recorded under.
WOUNDING = "wounding"


def characteristic_roll_of(combatant: Any, characteristic: str) -> int:
    """His Characteristic Roll (9 + CHAR/5, rounded), from kirby-cost.

    The canon rounds; a local `9 + X // 5` truncates and disagrees on 16 of
    40 values (see `session.tie_rule`). A built character reads his sheet
    and his campaign's roll constants, as `perception.per_roll_target`
    does; a stat block reads `combat_stats()`, and has no default.
    """
    from kirby_cost.engine.rolls import characteristic_roll, roll_constants

    hero = getattr(combatant, "hero", None)
    if hero is not None:
        base, denominator = roll_constants(hero)
        value = hero.characteristic_value(characteristic.upper())
    else:
        base, denominator = roll_constants(None)
        value = getattr(combatant.combat_stats(), characteristic.lower())
    return characteristic_roll(value, base=base, denominator=denominator)


def wounding_target(combatant: Any, *, body_taken: int) -> int:
    """The EGO Roll a man makes after taking ``body_taken`` BODY (6E2 p.110)."""
    return characteristic_roll_of(combatant, "EGO") - int(body_taken) // BODY_PER_POINT


def _made(roll: int, needed: int) -> bool:
    if roll == ALWAYS_MAKES:
        return True
    if roll == ALWAYS_FAILS:
        return False
    return roll <= needed


def wounding_check(session: "CombatSession", target_id: str, body_taken: int, *,
                   roller) -> dict | None:
    """The EGO Roll, as the row records it; None when no BODY got through."""
    if body_taken <= 0 or target_id not in session.combatants:
        return None
    needed = wounding_target(session.combatants[target_id], body_taken=body_taken)
    roll = sum(roller.roll_dice(3, 6))
    return {"target_id": target_id, "roll": roll, "needed": needed,
            "flinched": not _made(roll, needed)}


def after_the_wound(session: "CombatSession", target_id: str, body_taken: int, *,
                    roller, template) -> dict:
    """What the lethality options make of BODY taken. Payload keys for the row."""
    out: dict[str, Any] = {}
    if template.use_wounding:
        check = wounding_check(session, target_id, body_taken, roller=roller)
        if check is not None:
            out[WOUNDING] = check
    return out


def flinching(session: "CombatSession", combatant_id: str) -> bool:
    """Whether a failed Wounding roll still takes his offence (6E2 p.110).

    From the last failed roll against him until he spends a Phase.
    """
    flinched = False
    for event in session.event_log:
        kind = getattr(event, "kind", "")
        if kind == "PhaseSpent" and getattr(event, "combatant_id", None) == combatant_id:
            flinched = False
            continue
        payload = getattr(event, "result_payload", None)
        if not isinstance(payload, dict):
            continue
        check = payload.get(WOUNDING)
        if check and check.get("target_id") == combatant_id and check.get("flinched"):
            flinched = True
    return flinched


def without_offence(menu: Iterable) -> list:
    """The menu a flinching man is offered: neutral and defensive only."""
    return [a for a in menu if a.kind in NON_OFFENSIVE_KINDS]
