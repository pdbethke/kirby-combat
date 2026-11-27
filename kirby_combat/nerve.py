"""Nerve: the PRE Roll a man makes when his side is breaking, and what failing does.

THE RULE. Western Hero p.128, on PRE Rolls: "you can use them to help
determine a character's reaction in situations that don't involve specific
Presence Attacks. For example, you might make a PRE roll for a person facing
overwhelming odds to resist fleeing." 6E1 p.47: PRE is "bravery,
confidence". And the outcome the book already names, 6E2 p.139 (a cowed
man): "He may surrender, run away, or faint."

RULINGS (Peter, 2026-11-27), because the book leaves when, by how much and
what failing means to the GM:

  * THE ROLL is a PRE Roll (9 + PRE/5), not EGO.
  * WHEN: at the top of his Phase, while his side is SHAKEN or worse
    (`morale.side_morale`, the casualty tiers the engine already keeps). A
    man who held rolls again next Phase if it is still that bad.
  * WHO NEVER ROLLS: a fearless complication (`courage.FEARLESS`: Vengeful,
    No fear of death ...) or one that holds him fast (`morale.holds_fast`).
  * PENALTIES: a cowardly complication (`courage.COWARDLY`) -3, or -5 when
    its intensity is Strong or Total; -1 for each wound he carries; -2 with
    no attack to fight with.
  * FAILING: he flees if he can --- legs under him and nobody holding him ---
    and surrenders if he cannot. A man who flees breaks off every Phase
    until he is gone (`flee_menu`); a man who surrenders is out of the
    fight: he takes no action, he no longer stands for his side
    (`roster.Roster.standing`), and nobody is offered a shot at him.

"Each wound he carries" is read as each active Impairing or Disabling wound
(`wounds.active_wounds`) plus one for each full quarter of his STUN gone.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession

HELD, FLED, SURRENDERED = "held", "fled", "surrendered"

COWARD_MODERATE, COWARD_STRONG = -3, -5
PER_WOUND = -1
UNARMED = -2
#: Western Hero and 6E2 p.105's ladder of how hurt: a quarter of his STUN.
STUN_QUARTER = 4

#: What a fleeing man may do: break off (`disengage`) and nothing else. He
#: is not choosing.
FLEE_KINDS = frozenset({"disengage"})


def _side(session, combatant) -> list:
    from kirby_combat.side import Side

    mine = Side.of(combatant)
    return [c for c in session.combatants.values() if Side.of(c) == mine]


def shaken(session, combatant) -> bool:
    """His side is SHAKEN or worse: overwhelming odds, in the engine's terms."""
    from kirby_combat.masscombat import UnitMorale
    from kirby_combat.morale import side_morale

    return side_morale(session, _side(session, combatant)) in (
        UnitMorale.SHAKEN, UnitMorale.ROUTING, UnitMorale.BROKEN)


def fearless(combatant) -> bool:
    from kirby_combat.complications import complications_of
    from kirby_combat.courage import FEARLESS, complication_saying
    from kirby_combat.morale import holds_fast

    return (complication_saying(complications_of(combatant), FEARLESS) is not None
            or holds_fast(combatant))


def modifiers(session, combatant) -> list[tuple[str, int]]:
    """Each penalty to his roll, labelled (rulings above)."""
    from kirby_combat.complications import complications_of
    from kirby_combat.courage import COWARDLY, complication_saying
    from kirby_combat.wounds import active_wounds

    out: list[tuple[str, int]] = []
    coward = complication_saying(complications_of(combatant), COWARDLY)
    if coward is not None:
        strong = (coward.adders or {}).get("INTENSITY") in ("STRONG", "TOTAL")
        out.append((coward.name, COWARD_STRONG if strong else COWARD_MODERATE))
    wounds = len(active_wounds(session, combatant.id))
    max_stun = int(getattr(combatant, "max_stun", 0) or 0)
    if max_stun > 0:
        lost = max_stun - int(combatant.state.current_stun)
        wounds += max(0, lost) * STUN_QUARTER // max_stun
    if wounds:
        out.append((f"{wounds} wound(s)", PER_WOUND * wounds))
    if not getattr(combatant, "attacks", None):
        out.append(("unarmed", UNARMED))
    return out


def can_flee(session, combatant_id: str) -> bool:
    """Legs under him and nobody holding him."""
    from kirby_combat.statuses import ENTANGLED, GRAB, statuses_for
    from kirby_combat.wounds import LEG, active_wounds

    if any(w["region"] == LEG for w in active_wounds(session, combatant_id)):
        return False
    return not ({ENTANGLED, GRAB} & statuses_for(session, combatant_id))


def nerve_state(session, combatant_id: str) -> str | None:
    """``fled`` or ``surrendered`` once he has broken; None while he holds.

    The latest failed roll wins and stays: a man who ran keeps running, and
    a surrender is not taken back.
    """
    state = None
    for event in session.event_log:
        if (getattr(event, "kind", "") == "NerveRolled"
                and event.combatant_id == combatant_id
                and event.outcome in (FLED, SURRENDERED)):
            state = event.outcome
    return state


def nerve_check(session: "CombatSession", combatant_id: str, *, roller) -> "CombatSession":
    """At the top of his Phase: roll, when the rulings say he must."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import NerveRolled, make_author_engine
    from kirby_combat.wounds import _made, characteristic_roll_of

    man = session.combatants[combatant_id]
    if nerve_state(session, combatant_id) is not None:
        return session
    if not shaken(session, man) or fearless(man):
        return session
    mods = modifiers(session, man)
    needed = characteristic_roll_of(man, "PRE") + sum(v for _l, v in mods)
    roll = sum(roller.roll_dice(3, 6))
    if _made(roll, needed):
        outcome = HELD
    else:
        outcome = FLED if can_flee(session, combatant_id) else SURRENDERED
    return apply_event(session, NerveRolled(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id=combatant_id, roll=roll, needed=needed,
        modifiers=tuple(f"{l}:{v:+d}" for l, v in mods), outcome=outcome))


def flee_menu(menu) -> list:
    """What a man who has broken may do: break off."""
    return [a for a in menu if a.kind in FLEE_KINDS]
