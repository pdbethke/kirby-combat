"""The readable projection of a session — what a viewer checks itself against.

A consumer that folds this engine's event log for display holds a copy of
what the log means, and a copy nothing checks is the defect this package
has already paid for twice. So the engine publishes the shape, and every
value on it is read through the engine's own door rather than derived a
second time here.

NOTHING HERE IS A RULE. Every field is a read: `classify_health` for the
rung, `is_down` for whether he is still in it, `Side.of` for whose part he
is on, `position_of` for where he stands, `statuses_for` for his
conditions, `concealment.perceives` for what he can see, `next_actor_id`
for whose Phase is next. A second reading of any of them here would be exactly
the drift this view exists to catch.

DELIBERATELY FLAT. It carries no build, no powers and no scene geometry —
a viewer that needs those reads the record. What it does carry is
everything a board draws: where he is, which way he faces, what condition
he is in, and who he can see.

`rewind_to_sequence` is what makes this a playback surface: a session
rewound to sequence N, projected here, is the fight as it stood at N.

AND PLAYBACK IS WHY `roller` IS REQUIRED AND HAS NO DEFAULT. Almost every
field here is a read, but perception is not quite: `perceive` rolls a PER
for an Invisible target's Fringe within 2 m and an opposed Stealth
contest for a Hidden one. A view that made its own roller would answer
differently every time it was asked about the same sequence, so two reads
of one moment would disagree and a replay would not be a replay. The
caller supplies the roller --- derived from the sequence, if it wants the
same answer twice --- and a caller that has not thought about it gets a
TypeError rather than a silent reseed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kirby_combat.concealment import is_invisible
from kirby_combat.concealment import perceives as _perceives
from kirby_combat.enumeration import is_down
from kirby_combat.health import classify_health
from kirby_combat.loop.run import next_actor_id as _next_actor_id
from kirby_combat.scene.placement import position_of
from kirby_combat.side import Side
from kirby_combat.statuses import KNOCKED_OUT, PRONE, STUNNED, statuses_for

if TYPE_CHECKING:
    from kirby_combat.session.combat_session import CombatSession


@dataclass(frozen=True)
class PositionView:
    """Metres and radians, 0 rad = east — `scene.Position`, flattened.

    A separate type rather than `Position` itself so the published shape
    does not drag `scene` into every consumer's generated types.
    """

    x: float
    y: float
    z: float
    facing: float


@dataclass(frozen=True)
class CombatantStateView:
    """One fighter as the folded log leaves them."""

    id: str
    name: str
    #: `None` is the solo case — every fighter his own part, which is what
    #: a free-for-all is. Not a missing value.
    side: str | None
    current_stun: int
    current_body: int
    current_end: int
    max_stun: int
    max_body: int
    max_end: int
    #: `classify_health`'s rung, verbatim.
    health: str
    #: `is_down`, verbatim: has he stopped fighting.
    down: bool
    #: `None` when he is not on the map. NOT the origin — a combatant with
    #: no position is absent from every distance, not adjacent to whoever
    #: stands at (0, 0, 0).
    position: PositionView | None
    #: Folded out of the log by `statuses_for`, which is the one door every
    #: condition source goes through.
    prone: bool
    stunned: bool
    ko: bool
    #: Whether the BUILD carries Invisibility at all, per
    #: `concealment.is_invisible` — a standing fact about the character,
    #: which is why it sits beside the conditions rather than inside
    #: anyone's `perceives`.
    #:
    #: NOT a second statement of who can see him. Being unseen is
    #: PAIRWISE and lives in `perceives` alone; a fighter who is Hidden
    #: from one enemy and watched by another has no single answer, so
    #: none is published. Invisibility is different: it is bought on the
    #: sheet, it is true of him rather than of a pair, and a board wants
    #: to draw it.
    invisible: bool
    #: The ids of the other combatants this one can perceive, through
    #: `concealment.perceives` — the one door that hands the log's
    #: concealment and the build's Invisibility to `perception.perceive`
    #: together, with his own Flash. Folds a Flash on his Sense Group, a
    #: Darkness field on the ray, Invisibility, a Hidden target's Stealth
    #: contest and the walls, all at once. Never contains his own id.
    #:
    #: THIS IS WHERE UNSEEN-NESS LIVES, and it is per observer, which is
    #: the granularity the engine's own Hide contest resolves at: one
    #: enemy may lose a man while another keeps him in view.
    #:
    #: NOT ALWAYS A READ. `perceive` rolls in exactly two places — the
    #: PER roll for an Invisible target's Fringe within 2 m, and a Hidden
    #: target's opposed Stealth contest — so those two pair kinds are a
    #: roll and not a projection. Every other pair is deterministic. That
    #: is what `state_view`'s required `roller` is for: one roller, one
    #: answer, and the same answer again for the same sequence.
    perceives: list[str]


@dataclass(frozen=True)
class SessionStateView:
    """Where the fight stands: the clock, the status and the men."""

    status: str
    turn: int
    segment: int
    #: THE HIGHEST `sequence` on the log, or 0 for a fight in which
    #: nothing has happened. `SessionStarted` IS stored, at sequence 1, so
    #: a length is the last sequence and not one off it — but a log
    #: holding only that event is a fight that has not started trading
    #: blows, and it answers 0 rather than 1. The GUARD is a length; the
    #: ANSWER is read off the event, never counted from it — a count
    #: would be a second statement of a number the log already carries,
    #: and the arithmetic that looks right is wrong the day an event is
    #: minted without being stored.
    last_sequence: int
    #: Whose Phase is next, or `None` when the fight is decided.
    #: `next_actor_id` is a QUESTION and spends no slot — it used to spend
    #: the slot of anyone it passed over, so asking changed the fight.
    next_actor_id: str | None
    combatants: list[CombatantStateView]


def _combatant_view(
    session: "CombatSession", combatant, roller,
) -> CombatantStateView:
    side = Side.of(combatant)
    held = statuses_for(session, str(combatant.id))
    at = position_of(session.scene, str(combatant.id))
    return CombatantStateView(
        id=str(combatant.id),
        name=str(combatant.name),
        side=None if side.is_solo else side.id,
        current_stun=int(combatant.current_stun),
        current_body=int(combatant.current_body),
        current_end=int(combatant.current_end),
        max_stun=int(combatant.max_stun),
        max_body=int(combatant.max_body),
        max_end=int(combatant.max_end),
        health=classify_health(combatant),
        down=is_down(combatant),
        position=None if at is None else PositionView(
            x=float(at.x), y=float(at.y), z=float(at.z),
            facing=float(at.facing),
        ),
        prone=PRONE in held,
        stunned=STUNNED in held,
        ko=KNOCKED_OUT in held,
        invisible=is_invisible(combatant),
        perceives=sorted(
            str(other.id) for other in session.combatants.values()
            if str(other.id) != str(combatant.id)
            and _perceives(session, combatant, other, roller=roller)
        ),
    )


def state_view(session: "CombatSession", *, roller) -> SessionStateView:
    """The fight as it stands, in the shape a viewer is checked against.

    `roller` is REQUIRED and keyword-only. See the module docstring: the
    perception fold rolls for two pair kinds, so a self-seeded roller
    would make two reads of one sequence disagree. A caller replaying a
    fight passes a roller derived from the sequence it is asking about.
    """
    return SessionStateView(
        status=session.status,
        turn=session.timeline.turn,
        segment=session.timeline.segment,
        last_sequence=(
            session.event_log[-1].sequence
            if len(session.event_log) > 1 else 0
        ),
        next_actor_id=_next_actor_id(session),
        combatants=[
            _combatant_view(session, c, roller)
            for c in session.combatants.values()
        ],
    )


__all__ = [
    "CombatantStateView", "PositionView", "SessionStateView", "state_view",
]
