"""A standing Block meeting the blow it was raised against (6E2 p.59-60).

THE BLOCK USED TO STOP NOTHING. `Block.resolve` rolled the contest and
`resolve_block_in_session` wrote it down, and the attack path never asked:
a man could Block, win, and take the punch anyway. The `block` resolver rolled
its contest in the blocker's own Phase against the attacker's BARE OCV, with no
attack in the air at all, so the roll was against nothing and stopped nothing.

6E2 p.59 puts the roll where the attack is: "A character who wants to Block
must declare his intention before his attacker makes an Attack Roll. To
attempt a Block, he must make an Attack Roll against his opponent's OCV (not
DCV). This is his opponent's OCV as modified by the attack the opponent is
making." So a Block is DECLARED (on his Phase, or by Aborting to it,
`loop/reactions.py`) as an `AbortDeclared(to_action="block")`, and it is
ROLLED here, from the attack door, when a hand-to-hand blow arrives:

* "If he succeeds, he Blocks the attack and takes no damage (and no
  Knockdown or Knockback)" --- the door records the attack as stopped.
* "If the Block misses, the attack doesn't automatically hit the Blocker; the
  attacker still has to succeed with his Attack Roll" --- the door carries on.
* 6E2 p.60: a man who has Blocked "can Block additional attacks made against
  him (by the same or different characters) ... before his next Phase", each
  at a cumulative -2; "If the character misses any of his Blocks, he cannot
  Block further attacks."
* 6E2 p.59: "Blocks only affect Ranged attacks with the GM's permission" ---
  only hand-to-hand attacks are Blocked here.
* 6E2 p.60: "Generally, a character cannot Block an attack he cannot
  perceive" --- the engine's one perception predicate decides.

The CV bonuses of a Block "are general ones" (6E2 p.59): `block_dcv_bonus`
is folded onto every attack at the door, the way `Dodge.dcv_bonus` is. A
bought Martial Block supplies both numbers (`actions/reactive/martial.py`).

NOT MODELLED: 6E2 p.60's optional -1 to -3 for an unarmed Block against a
weapon, shields and Off-Hand Defense (each a GM option the engine has no
campaign switch for), and Blocking for someone else at -2.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kirby_combat.actions.reactive.block import BlockResult
from kirby_combat.actions.reactive.martial import block_maneuver

if TYPE_CHECKING:
    from kirby_combat.models import AttackInput
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate

#: 6E2 p.60: "Each additional roll is made at a cumulative -2 penalty".
ADDITIONAL_BLOCK_PENALTY = -2

#: The ``to_action`` an Abort or a declared Block records.
BLOCK = "block"


def standing_block_id(session: "CombatSession", combatant_id: str) -> str | None:
    """The id of the `AbortDeclared` his current Block stands on, or None.

    The window on the timeline says whether a Block is standing (it closes
    when his next Phase is spent, 6E2 p.24's "until his next Phase after
    that"); the declaration's id is what each roll against it is recorded
    under, so the cumulative penalty can be counted off the log.
    """
    window = session.timeline.aborts.get(combatant_id)
    if window is None or window.to_action != BLOCK:
        return None
    for event in reversed(session.event_log):
        if (getattr(event, "kind", "") == "AbortDeclared"
                and event.combatant_id == combatant_id):
            return event.id
    raise ValueError(
        f"{combatant_id!r} has a Block window on the timeline and no "
        "AbortDeclared in the log that opened it"
    )


def blocks_rolled(session: "CombatSession", declaration_id: str) -> list[dict[str, Any]]:
    """Every Block roll made against one declaration, oldest first."""
    out: list[dict[str, Any]] = []
    for event in session.event_log:
        payload = getattr(event, "result_payload", None)
        if (isinstance(payload, dict) and payload.get("kind") == BLOCK
                and getattr(event, "declaration_event_id", None) == declaration_id):
            out.append(payload)
    return out


def block_dcv_bonus(session: "CombatSession", combatant_id: str) -> int:
    """The DCV his standing Block gives against every attack (6E2 p.59).

    +0 for the plain maneuver; a Martial Block's DCV column (+2 on 6E2
    p.93's table) when he bought one.
    """
    if standing_block_id(session, combatant_id) is None:
        return 0
    return block_maneuver(session.combatants[combatant_id]).dcv


def try_block(
    session: "CombatSession", attack: "AttackInput", template: "CombatTemplate",
    *, combat_type: str, roller,
) -> tuple["CombatSession", BlockResult | None]:
    """Roll the target's standing Block against this attack, if it can apply.

    Returns the session with the roll recorded (an ``ActionResolved`` of
    kind ``"block"`` under his declaration, plus 6E2 p.60's
    ``BlockPriorityGained`` on a success) and the result --- or the session
    untouched and ``None`` when no Block applies to this attack.

    ``attack`` must be the attack AS IT WILL BE ROLLED --- every per-fight
    condition already folded on --- because the Block is rolled against
    "his opponent's OCV as modified by the attack the opponent is making".
    """
    from kirby_combat.actions.recording import resolve_block_in_session
    from kirby_combat.cv_modifiers import effective_ocv_for
    from kirby_combat.enumeration import is_down
    from kirby_combat.resolution.to_hit import resolve_to_hit
    from kirby_combat.sense_penalties import HTH, cannot_perceive

    blocker_id = getattr(attack.target, "id", None)
    attacker_id = getattr(attack.attacker, "id", None)
    if blocker_id not in session.combatants or attacker_id not in session.combatants:
        return session, None
    declaration_id = standing_block_id(session, blocker_id)
    if declaration_id is None:
        return session, None
    if combat_type != HTH:
        return session, None                  # 6E2 p.59: HTH attacks only
    blocker = session.combatants[blocker_id]
    if is_down(blocker):
        return session, None
    if cannot_perceive(session, blocker, session.combatants[attacker_id]):
        return session, None                  # 6E2 p.60
    earlier = blocks_rolled(session, declaration_id)
    if any(not p.get("success") for p in earlier):
        return session, None                  # 6E2 p.60: one miss ends it

    attacker_ocv = int(resolve_to_hit(attack, template).effective_ocv)
    blocker_ocv = (
        effective_ocv_for(session, blocker_id, against=attacker_id, combat_type=HTH)
        + block_maneuver(blocker).ocv
        + ADDITIONAL_BLOCK_PENALTY * len(earlier)
    )
    session, result, _priority = resolve_block_in_session(
        session,
        blocker_id=blocker_id, attacker_id=attacker_id,
        blocker_ocv=int(blocker_ocv), blocker_dice=roller.roll_dice(3),
        attacker_ocv=attacker_ocv,
        declaration_event_id=declaration_id,
    )
    return session, result
