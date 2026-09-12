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
    #: Allies who are DOWN. Separate from `allies` --- see
    #: `kirby_combat.tactics.base.Situation.fallen_allies`.
    fallen_allies: list[Any] = field(default_factory=list)
    #: enemy_id -> metres. Handed on to the tactic layer, which could not
    #: previously ask how far anybody was --- see
    #: `kirby_combat.tactics.base.Situation.distances_m`.
    distances_m: dict[str, float] = field(default_factory=dict)
    #: The actor's melee reach in metres (6E2 p.56).
    reach_m: float = 1.0
    session: "CombatSession | None" = None
    segment: int = 0
    turn: int = 1

    @property
    def action_ids(self) -> list[str]:
        return [a.action_id for a in self.menu]

    @property
    def ordered_menu(self) -> list[LegalAction]:
        """The same offers, with scenery at the bottom.

        MEN BEFORE BUILDINGS. Virgil Earp takes cover behind Fly's Studio,
        where no Cowboy can be seen and so no offer against a Cowboy
        survives the perception gate. Doctrine correctly declines, the
        fallback takes the first legal offer --- and the first legal offer
        is ``attack:construct:harwood-interior``. The marshal of Tombstone
        spends his Phase shooting a house.

        ``LegalAction.targets_construct`` was added for exactly this and
        says so: "Terrain offers led the action list --- six of the first
        six entries in a 21-action menu --- while 'Flight toward <enemy>'
        sat at #18, so the picker spent 8 of 19 real actions demolishing
        scenery. Used for PRESENTATION ORDER only; the legal set is
        unchanged." It was set in three places, read by the resolver to
        route damage, and NOTHING EVER ORDERED ON IT.

        Here rather than in ``enumerate_actions`` because that function
        answers what is LEGAL and this object is the presentation of it.

        A stable partition, not a sort: relative order within each group
        is exactly what the enumerator decided. And the legal set is
        untouched --- when a wall is all there is, a wall is what he hits.
        """
        if not self.menu:
            return []
        real = [a for a in self.menu if not getattr(a, "targets_construct", False)]
        scenery = [a for a in self.menu if getattr(a, "targets_construct", False)]
        return real + scenery

    def brief(self):
        """This Phase written down, for a chooser that reads text.

        See ``kirby_combat.brief``. Imported lazily because a Brief is a
        view of a situation and a situation must not need one to exist.
        """
        from kirby_combat.brief import Brief

        return Brief(self)

    @property
    def targetable_enemies(self) -> list[Any]:
        """The enemies at least one offer on the menu names.

        WHO YOU MAY PLAN AGAINST, which is not the same question as who is
        in the fight. Measured over 25 seeded O.K. Corral runs: 142 of 638
        decisions fell through the entire tactic catalogue to
        ``FirstLegalChooser``, and Virgil Earp --- who spends the fight
        behind Fly's Studio, a LoS-blocking wall --- fell through on 51%
        of his own. Six tactics in a row named ``virgil_earp``, the
        perception gate had already dropped every offer against a man
        nobody could see, and so every plan was unexecutable.

        Perception governs combat here; an AI cannot target an enemy it
        cannot perceive. That was enforced on the MENU and never on the
        SITUATION, so doctrine went on making plans about a man it had no
        business knowing the position of.

        This re-derives none of it. The menu has already applied
        perception, range, reach, ammunition, frameworks and aborts, so
        reading the menu gets all of them for free --- including the one
        case where an enemy you cannot see is still fair game: an adjacent
        HtH offer survives the gate marked ``blind`` and keeps him on the
        list.

        Construct offers are excluded: ``attack_construct`` is keyed by
        WALL id, and a wall must never put a fighter back on the roll.

        An EMPTY menu filters nothing. A caller assembling a Situation
        without one is not claiming nobody is targetable, and blanking
        every enemy list there would be a silent, total change.
        """
        if not self.menu:
            return list(self.enemies)
        named = {
            a.target_id for a in self.menu
            if a.target_id and not getattr(a, "targets_construct", False)
        }
        return [e for e in self.enemies if getattr(e, "id", None) in named]

    def tactical_situation(self) -> Situation:
        """This Phase as the ``Situation`` the tactic catalogue consumes."""
        targetable = self.targetable_enemies
        return Situation(
            actor=self.actor,
            allies=list(self.allies),
            fallen_allies=list(self.fallen_allies),
            distances_m=dict(self.distances_m),
            reach_m=self.reach_m,
            # NOT ``self.enemies`` --- see ``targetable_enemies``.
            enemies=list(targetable),
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
                getattr(e, "id", ""): complications_of(e) for e in targetable
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
        # `ordered_menu`, not `menu`: taking the first LEGAL offer must not
        # mean taking the first BUILDING. See `PhaseSituation.ordered_menu`.
        return situation.ordered_menu[0].action_id


@dataclass
class TacticPick:
    """One decision and the doctrine behind it.

    `ModelChooser` keeps the same record for the same reason --- "a fight
    driven by a model is worth being able to explain afterwards". A fight
    driven by DOCTRINE is worth it more, because doctrine can cite a page:
    `basis` is either a rulebook reference or a stated judgement, and it
    is what makes a choice arguable with a GM rather than merely observed.

    Without this the doctrine layer was unmeasurable. You could not ask
    which tactics fire, which never fire, or which correlate with winning
    --- and attributing picks after the fact is guesswork, because several
    tactics emit `attack` and only the chooser knows which one it took.
    """

    action_id: str
    tactic: str | None = None
    rationale: str = ""
    basis: str = ""
    fell_back: bool = False
    #: WHO decided and WHEN. Without these a record of decisions cannot
    #: answer "does this fighter fall through more than that one", which
    #: is the first question anyone asks of it.
    actor_id: str = ""
    turn: int = 0
    segment: int = 0


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
        #: Every decision, in order, with the doctrine that made it.
        self.picks: list[TacticPick] = []

    def _record(self, action_id: str, tactic=None, plan=None,
                fell_back: bool = False, situation=None) -> str:
        basis = getattr(tactic, "basis", None) if tactic else None
        self.picks.append(TacticPick(
            action_id=action_id,
            tactic=getattr(tactic, "name", None) if tactic else None,
            rationale=getattr(plan, "rationale", "") if plan else "",
            basis=(getattr(basis, "judgement", "")
                   or getattr(basis, "rulebook", "") or "") if basis else "",
            fell_back=fell_back,
            actor_id=getattr(getattr(situation, "actor", None), "id", ""),
            turn=getattr(situation, "turn", 0) or 0,
            segment=getattr(situation, "segment", 0) or 0,
        ))
        return action_id

    def choose(self, situation: PhaseSituation) -> str:
        if not situation.menu:
            raise InvalidChoice("<empty menu>", [])

        by_kind: dict[str, list[LegalAction]] = {}
        # Scenery last here too: a tactic that names a kind but no target
        # takes `offers[0]`, and `attack` offers include every wall on the
        # map. Same reason as the fallback.
        for action in situation.ordered_menu:
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
                return self._record(aimed[0].action_id, tactic, plan,
                                    situation=situation)
            return self._record(offers[0].action_id, tactic, plan,
                                situation=situation)

        # Falling through to the fallback IS a decision, and this class
        # says so --- but it must be visible as one, or a fight driven
        # entirely by the fallback reads as doctrine working.
        return self._record(self._fallback.choose(situation), fell_back=True,
                            situation=situation)

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
