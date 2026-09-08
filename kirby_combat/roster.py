"""Roster — the sides of one fight, and who is still standing.

WHY A CLASS AND NOT FOUR FUNCTIONS. This began as ``side_of(combatant)``,
``standing_sides(session)``, ``last_side_standing(session)`` and
``validate_sides(session)`` --- four module-level helpers that all took the
same object as their first argument, which is a class waiting to be written.
A Roster holds the session once and answers questions about it, so a caller
asks ``roster.enemies_of(actor)`` rather than assembling the same
comprehension at every call site (the loop had two of them).

Things answer questions about themselves: ``side.is_solo``, not
``is_solo(side)``; ``roster.decided``, not ``last_side_standing(session)``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Protocol, runtime_checkable

from kirby_combat.enumeration import is_down
from kirby_combat.side import Side

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


class AmbiguousSides(Exception):
    """Two distinct sides in one fight share a display name.

    Far rarer now that ``Side`` is an object --- ``Side.named`` folds case
    and spacing into one id, so the common typo cannot produce two sides at
    all. This catches what remains: two Sides with DIFFERENT ids presenting
    the same name, which would report an ambiguous winner.
    """


class UnexpectedSide(Exception):
    """A combatant is on a side the caller did not declare.

    The only way to catch a real misspelling. ``Side.named("Goldne")`` is a
    perfectly good side as far as the roster is concerned; only someone who
    knows the intended armies can say it is wrong.
    """


@dataclass(frozen=True)
class Verdict:
    """Whether the fight is over, and who won.

    An object rather than a ``(bool, Side | None)`` tuple: a caller reads
    ``verdict.winner`` instead of remembering which slot it was in, and
    ``if verdict:`` asks the obvious question.
    """

    over: bool
    winner: Side | None = None

    def __bool__(self) -> bool:
        return self.over

    def __str__(self) -> str:
        if not self.over:
            return "undecided"
        return f"{self.winner} wins" if self.winner else "mutual knockout"


@runtime_checkable
class StopCondition(Protocol):
    """Decides whether a fight has ended. ``LastSideStanding`` is the default."""

    def decide(self, roster: "Roster") -> Verdict: ...


class LastSideStanding:
    """Over when at most one side still has someone up.

    Deliberately NOT "one combatant left": a four-army battle ends when
    three armies are down, however many soldiers the fourth still has. A
    mutual knockout is a real outcome --- ``over`` with no ``winner`` ---
    not a draw to be broken.
    """

    def decide(self, roster: "Roster") -> Verdict:
        standing = roster.standing
        if len(standing) > 1:
            return Verdict(over=False)
        if not standing:
            return Verdict(over=True, winner=None)
        return Verdict(over=True, winner=next(iter(standing)))


class Roster:
    """The combatants in one fight, grouped by the side they fight for."""

    def __init__(self, session: "CombatSession") -> None:
        self._session = session

    @property
    def combatants(self) -> list:
        return list(self._session.combatants.values())

    def _has_left(self, combatant_id: str) -> bool:
        """Outside the scene's bounds --- i.e. no longer on the field.

        No scene, no bounds, or no position for this combatant means the
        question does not arise: most fights are on no map at all, and
        they must keep working exactly as before.
        """
        scene = getattr(self._session, "scene", None)
        if scene is None:
            return False
        bounds = getattr(scene, "bounds", None)
        pos = (getattr(scene, "combatant_positions", None) or {}).get(combatant_id)
        if bounds is None or pos is None:
            return False
        return not (
            bounds.min_x <= pos.x <= bounds.max_x
            and bounds.min_y <= pos.y <= bounds.max_y
        )

    @property
    def standing(self) -> dict[Side, list[str]]:
        """Each side with at least one combatant still up, to their ids.

        "Up" is ``not is_down``: 6E1 p.421 --- knocked out at STUN <= 0,
        dying at BODY <= 0. A side present but wholly down does not appear.
        Keyed by ``Side``, which hashes on its id, so it groups correctly
        whether or not every combatant was handed the same instance.

        AND NOT GONE. Those two were the only ways this knew a fighter
        could stop, so every fight the engine ran ended in unconsciousness
        --- there was no way to leave. A combatant beyond the scene's
        ``SceneBounds`` has left the field ("Combatants must stay within",
        per its own docstring) and is no longer in the fight, so a side
        whose last member has run does not appear here and the fight ends.

        Read off the POSITION rather than a flag, so it cannot fall out of
        step with where the combatant actually is --- and so a fighter
        carried back inside by anything is simply in the fight again.
        """
        out: dict[Side, list[str]] = {}
        for combatant in self.combatants:
            if is_down(combatant) or self._has_left(combatant.id):
                continue
            out.setdefault(Side.of(combatant), []).append(combatant.id)
        return out

    @property
    def sides(self) -> frozenset[Side]:
        """Every side present, standing or not."""
        return frozenset(Side.of(c) for c in self.combatants)

    def enemies_of(self, actor) -> list:
        """Everyone still up who is not on the actor's side."""
        mine = Side.of(actor)
        return [
            c for c in self.combatants
            if Side.of(c) != mine and not is_down(c)
        ]

    def allies_of(self, actor) -> list:
        """Everyone else still up on the actor's side."""
        mine = Side.of(actor)
        return [
            c for c in self.combatants
            if c.id != actor.id and Side.of(c) == mine and not is_down(c)
        ]

    def decide(self, condition: StopCondition | None = None) -> Verdict:
        return (condition or LastSideStanding()).decide(self)

    def validate(self, *, expected: Iterable[Side] | None = None) -> None:
        """Raise if the roster's sides look like a mistake.

        **Ambiguity** --- two distinct sides presenting the same display
        name, which would report an ambiguous winner. **Unexpected sides**
        --- when ``expected`` is given, any non-solo side not among them,
        the only thing that catches a real misspelling.

        Solo sides are never unexpected: a lone bystander in a war between
        named armies was not claiming to be on one of them.
        """
        by_name: dict[str, set[Side]] = {}
        for combatant in self.combatants:
            side = Side.of(combatant)
            if side.is_solo:
                continue
            by_name.setdefault(side.name.strip().casefold(), set()).add(side)

        ambiguous = {n: s for n, s in by_name.items() if len(s) > 1}
        if ambiguous:
            detail = "; ".join(
                f"{name!r} is used by ids {sorted(x.id for x in sides)}"
                for name, sides in sorted(ambiguous.items())
            )
            raise AmbiguousSides(
                f"distinct sides sharing a display name, so a winner could not "
                f"be reported unambiguously: {detail}"
            )

        if expected is None:
            return
        allowed = {s.id for s in expected}
        stray = {s for sides in by_name.values() for s in sides if s.id not in allowed}
        if stray:
            raise UnexpectedSide(
                f"combatants on sides that were not declared: "
                f"{sorted(s.name for s in stray)}. "
                f"Declared: {sorted(s.name for s in expected)}"
            )
