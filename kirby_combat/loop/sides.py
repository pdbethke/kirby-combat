"""Sides — who is on whose team, and when the fight is decided.

The engine modelled no teams at all until 2026-09-06. The parked kirby-api
driver read a ``side`` column off ``combat_session_combatant`` rows and
aggregated up/down per side in 38 lines of SQL-backed code, which meant "who
is fighting whom" was a fact only the database knew. That is fight data, not
storage data: a fight cannot end without it, and ending a fight is a rule.

``side`` IS ``None`` MEANS A SIDE OF ONE. The tempting reading --- everyone
unlabelled shares one "default" side, which is literally what the kirby-api
column defaults to --- is wrong here, and wrong in a way that fails silently
in a case Kirby already ships. An N-way free-for-all (the Random Fight
button) labels nobody, so under a shared default every fighter would be on
one side, ``last_side_standing`` would be true before the first punch, and
the fight would end at Phase 0 with a winner. Treating an absent side as a
side of one makes every arrangement fall out of a single rule:

===========================  =========================  =====================
fight                        sides                      ends when
===========================  =========================  =====================
two teams                    "heroes" / "villains"      one team is down
three-way                    "a" / "b" / "c"            one side remains
the battle of four armies    four names, many each      one army remains
N-way free-for-all           all ``None``               one fighter remains
a team plus two loners       "pack", ``None``, ``None`` one side remains
===========================  =========================  =====================

Nothing caps the number of sides. Three is the same rule as two.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from kirby_combat.enumeration import is_down

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


def side_of(combatant) -> str:
    """The side this combatant fights for.

    An explicit ``side`` is used as given. ``None`` resolves to a side
    unique to this combatant, so unlabelled fighters are opponents rather
    than allies --- see the module docstring for why that default is the
    load-bearing one. The ``solo:`` prefix cannot collide with a caller's
    own label unless they choose to use it, in which case they have said
    those combatants are allies and that is what they get.
    """
    side = getattr(combatant, "side", None)
    return side if side else f"solo:{combatant.id}"


def standing_sides(session: "CombatSession") -> dict[str, list[str]]:
    """Map each side with at least one combatant still up to their ids.

    "Up" is ``not is_down`` (``kirby_combat.enumeration``): 6E1 p.421 ---
    knocked out at STUN <= 0, dying at BODY <= 0. A side present in the
    fight but wholly down does not appear.
    """
    out: dict[str, list[str]] = {}
    for combatant in session.combatants.values():
        if is_down(combatant):
            continue
        out.setdefault(side_of(combatant), []).append(combatant.id)
    return out


def last_side_standing(session: "CombatSession") -> tuple[bool, str | None]:
    """``(is_over, winning_side)`` --- the loop's default stop condition.

    Over when at most one side still has someone up. The winner is that
    side, or ``None`` when everyone is down (a mutual knockout is a real
    outcome, not a draw to be broken).

    Deliberately NOT "one combatant left": a four-army battle ends when
    three armies are down, however many soldiers the fourth still has.
    """
    sides = standing_sides(session)
    if len(sides) > 1:
        return False, None
    if not sides:
        return True, None
    return True, next(iter(sides))
