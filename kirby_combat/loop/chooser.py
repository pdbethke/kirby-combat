"""The seat — the one thing in a fight the engine does not decide.

Everything else about a Phase is a rule and belongs here: who has a Phase in
this Segment (6E2 p.18), who among them acts first (6E2 p.19-21), what they
may legally do (``enumerate_actions``), what that does when they do it, and
whether the fight is over (6E1 p.421). What remains is the choice, and the
engine takes that from a ``Chooser``.

A ``Chooser`` is synchronous and performs no I/O. Anything that consults a
model is a chooser implemented OUTSIDE this package --- in ``kirby-ai``, or
in the consumer --- and the engine never learns what is on the other end of
the protocol. That separation is structural rather than a convention:
``tests/test_vocabulary.py`` forbids this repo from naming such a thing even
in a comment.

TWO CHOOSERS SHIP HERE, both pure and both deterministic:

* ``FirstLegalChooser`` takes the first offer in menu order. It exists to
  make the loop testable --- a fight has to be drivable without anything
  clever in the seat --- and is explicitly not a tactic.
* ``TacticChooser`` classifies the actor with ``classify_role`` and takes
  its doctrine from ``tactics_for``. This is what makes the shipped role and
  tactic work load-bearing rather than advisory: doctrine that nothing ever
  consults is documentation.

A CHOICE OUTSIDE THE MENU IS AN ERROR. ``choose`` returns an ``action_id``
that must appear in the menu it was given. Returning anything else raises
``InvalidChoice`` at the seat rather than failing three frames deeper in a
resolver, or --- worse --- being quietly dropped, which is how a fight ends
up spending phases doing nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from kirby_combat.enumeration import LegalAction
from kirby_combat.roles import classify_role
from kirby_combat.complications import complications_of
from kirby_combat.tactics.base import Situation
from kirby_combat.tactics.library import tactics_for

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


class InvalidChoice(Exception):
    """A chooser returned an ``action_id`` that was not on the menu."""

    def __init__(self, action_id: str, offered: list[str]) -> None:
        self.action_id = action_id
        self.offered = offered
        super().__init__(
            f"chooser returned {action_id!r}, which was not offered; "
            f"the menu held {len(offered)} actions: {offered[:8]}"
            + (" ..." if len(offered) > 8 else "")
        )


@dataclass
class PhaseSituation:
    """What a chooser is shown when it is asked to decide one Phase.

    Deliberately a snapshot, not a handle on the engine: a chooser reads it
    and returns a string. It cannot resolve anything itself, which is what
    keeps the rules on this side of the seat.
    """

    actor: Any
    menu: list[LegalAction]
    enemies: list[Any] = field(default_factory=list)
    allies: list[Any] = field(default_factory=list)
    session: "CombatSession | None" = None
    segment: int = 0
    turn: int = 1

    @property
    def action_ids(self) -> list[str]:
        return [a.action_id for a in self.menu]

    def brief(self):
        """This Phase written down, for a chooser that reads text.

        See ``kirby_combat.brief``. Imported lazily because a Brief is a
        view of a situation and a situation must not need one to exist.
        """
        from kirby_combat.brief import Brief

        return Brief(self)

    def tactical_situation(self) -> Situation:
        """This Phase as the ``Situation`` the tactic catalogue consumes."""
        return Situation(
            actor=self.actor,
            allies=list(self.allies),
            enemies=list(self.enemies),
            current_segment=self.segment,
            turn=self.turn,
            # Carries the event log, which is the half of `threat` that is
            # WITNESSED rather than merely visible. Without it a fighter
            # can see who is holding the axe but never learns who used it.
            session=self.session,
            # Two tactics have read these since the day tactics existed and
            # the loop never filled them, so `bait_enraged` and
            # `exploit_susceptibility` have never once fired in a
            # loop-driven fight.
            actor_complications=complications_of(self.actor),
            enemy_complications={
                getattr(e, "id", ""): complications_of(e) for e in self.enemies
            },
        )


@runtime_checkable
class Chooser(Protocol):
    """Decides one Phase. Must return an ``action_id`` from the menu."""

    def choose(self, situation: PhaseSituation) -> str: ...


class FirstLegalChooser:
    """Takes the first offer, in menu order.

    Not a tactic and not a fallback for a cleverer chooser that failed ---
    it is the deterministic seat that makes the loop itself testable. A
    fight driven by this chooser exercises every rule in the loop while
    holding the decision constant, which is what lets a test attribute a
    change to the loop rather than to the picker.
    """

    name = "first-legal"

    def choose(self, situation: PhaseSituation) -> str:
        if not situation.menu:
            raise InvalidChoice("<empty menu>", [])
        return situation.menu[0].action_id


class TacticChooser:
    """Picks by role and doctrine.

    ``classify_role`` says what kind of fighter the actor is;
    ``tactics_for`` returns the tactics that apply to this situation, best
    first. Each tactic's ``execute`` emits a ``Plan`` whose first step names
    a ``kind`` and, in sixteen of the twenty-two, a ``target_id``; this
    chooser takes the strongest tactic whose first step matches something
    actually on the menu --- BOTH halves of it.

    WHEN DOCTRINE AND LEGALITY DISAGREE, LEGALITY WINS. A tactic may
    recommend a kind the actor cannot perform this Phase --- it is
    Entangled, the power is out of END, the target cannot be perceived.
    Enumeration has already applied those rules, so a recommendation absent
    from the menu is skipped rather than forced. Falling through every
    tactic leaves the first legal offer, which is a decision and not an
    error: a combatant with no applicable doctrine still has a Phase.
    """

    name = "tactic"

    def __init__(self, *, fallback: Chooser | None = None) -> None:
        self._fallback = fallback or FirstLegalChooser()

    def choose(self, situation: PhaseSituation) -> str:
        if not situation.menu:
            raise InvalidChoice("<empty menu>", [])

        by_kind: dict[str, list[LegalAction]] = {}
        for action in situation.menu:
            by_kind.setdefault(action.kind, []).append(action)

        tactical = situation.tactical_situation()
        for tactic in tactics_for(tactical):
            plan = tactic.execute(tactical)
            if not plan.steps:
                continue
            # A PLAN IS A SEQUENCE OF PREFERENCES, and this read one step
            # of it. `close_and_strike` plans [close, strike]: a melee
            # fighter whose enemy is at range has no attack on the menu,
            # so reading only the strike found nothing and fell through to
            # the fallback --- which is how Power Lad and the last Cowboy
            # stood two metres apart doing nothing to each other until the
            # stalemate guard fired.
            #
            # Same shape as this chooser discarding `target_id`: something
            # the tactics wrote and nothing read.
            for step in plan.steps:
                offers = by_kind.get(step.kind)
                if offers:
                    break
            else:
                continue
            # DOCTRINE NAMES A VICTIM, AND IT IS NOT DECORATION. Sixteen of
            # the catalogue's tactics set `target_id`; this read the kind
            # and took offers[0], which is the first offer in MENU order,
            # which is roster order. So for every fight this engine ran,
            # "who" was decided by where a combatant sat in the list.
            #
            # Found with Power Lad in the O.K. Corral: he killed seven men
            # and was shot at twice in twenty-five Phases, because he was
            # appended last and so was offer #5 of 5 for everybody.
            if step.target_id is not None:
                aimed = [o for o in offers if o.target_id == step.target_id]
                if not aimed:
                    # Legality wins, as this class already says. Firing the
                    # right KIND at the wrong MAN is worse than falling
                    # through, because it looks like a decision.
                    continue
                return aimed[0].action_id
            return offers[0].action_id

        return self._fallback.choose(situation)

    @staticmethod
    def role_of(combatant) -> str:
        """The actor's role, exposed so a caller can report what drove a
        pick without re-deriving it."""
        return classify_role(combatant)


def validate_choice(action_id: str, menu: list[LegalAction]) -> LegalAction:
    """Return the chosen ``LegalAction``, or raise ``InvalidChoice``.

    Called by the loop on every pick, including those from the choosers
    above --- a chooser is untrusted input by design, since the interesting
    ones are written elsewhere.
    """
    for action in menu:
        if action.action_id == action_id:
            return action
    raise InvalidChoice(action_id, [a.action_id for a in menu])
