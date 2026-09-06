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

import re
from typing import TYPE_CHECKING

from kirby_combat.enumeration import is_down

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


_WHITESPACE = re.compile(r"\s+")


class AmbiguousSides(Exception):
    """Two side labels in one fight differ only in case or spacing.

    Almost certainly one side written carelessly --- and left alone it is
    invisible: a four-army battle quietly becomes a five-army battle that
    ends differently, with nothing to look at.
    """


class UnexpectedSide(Exception):
    """A combatant is on a side the caller did not declare.

    The only way to catch a real misspelling. ``"Goldne"`` is a perfectly
    good side label as far as the roster is concerned; only someone who
    knows the intended armies can say it is wrong.
    """


def canonical_side(label: str | None) -> str:
    """The comparison key for a side label.

    Case-folded, trimmed, internal whitespace collapsed --- so ``"Golden"``,
    ``"golden"``, ``" Golden "`` and ``"Golden  Horde"`` vs
    ``"Golden Horde"`` compare equal. Returns ``""`` for a label that is
    empty or only whitespace, which is what makes ``side="   "`` fall
    through to the free-for-all default instead of naming an army of
    spaces.

    Used ONLY for comparison. The label a caller wrote is what gets
    reported back as the winner --- this never rewrites their spelling.
    """
    if not label:
        return ""
    return _WHITESPACE.sub(" ", label.strip()).casefold()


def validate_sides(session: "CombatSession", *, expected=None) -> None:
    """Raise if the roster's side labels look like a typo.

    Two checks, catching two different mistakes:

    * **Ambiguity** --- two distinct labels sharing a canonical form
      (``"Golden"`` and ``"golden"``). Detectable from the roster alone.
      Raises ``AmbiguousSides`` naming both spellings AND the combatants
      wearing them, because "you have two Goldens" is not actionable
      without knowing which soldiers are on the wrong one.
    * **Unexpected sides** --- when ``expected`` is given, any labelled
      combatant whose side is not in it. This is the only thing that
      catches ``"Goldne"``. Matching is canonical, so declaring
      ``"Golden"`` accepts a soldier labelled ``"golden"``: the set is a
      list of sides, not a spelling test.

    Unlabelled combatants are never unexpected --- they are their own
    side and were not claiming to be on a declared one, so a lone
    bystander in a war between named armies is legal.

    RAISING, NOT MERGING. Folding ``"golden"`` into ``"Golden"`` would fix
    the count and hide the defect, and would guess at intent the engine
    does not have. It reports what it found; the caller decides.
    """
    by_key: dict[str, dict[str, list[str]]] = {}
    for combatant in session.combatants.values():
        label = getattr(combatant, "side", None)
        key = canonical_side(label)
        if not key:
            continue
        by_key.setdefault(key, {}).setdefault(label, []).append(combatant.id)

    ambiguous = {k: v for k, v in by_key.items() if len(v) > 1}
    if ambiguous:
        groups = "; ".join(
            " vs ".join(
                f"{label!r} ({', '.join(sorted(ids))})"
                for label, ids in sorted(spellings.items())
            )
            for spellings in ambiguous.values()
        )
        raise AmbiguousSides(
            f"side labels differing only in case or spacing --- probably one "
            f"side written two ways, which would silently add an army: {groups}"
        )

    if expected is None:
        return

    allowed = {canonical_side(label) for label in expected}
    stray = {
        key: spellings for key, spellings in by_key.items() if key not in allowed
    }
    if stray:
        found = "; ".join(
            f"{label!r} ({', '.join(sorted(ids))})"
            for spellings in stray.values()
            for label, ids in sorted(spellings.items())
        )
        raise UnexpectedSide(
            f"combatants on sides that were not declared: {found}. "
            f"Declared sides: {sorted(expected)}"
        )


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
    return side if canonical_side(side) else f"solo:{combatant.id}"


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
