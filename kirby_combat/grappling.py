"""What a Grab costs the two men in it.

The engine could Grab, and a Grab changed nothing about anyone's combat
ability afterwards --- which makes grappling strictly free, and so never
worth doing to anybody you could simply shoot instead.

Western Hero p.104, the genre book for the western benchmarks, prices the
hold exactly, and 6E2 p.64-66 agrees:

    "Assuming the Grabber holds on, the Grabber and victim are now 1/2
     DCV. The Grabber is full OCV against the victim and the victim is -3
     OCV against the Grabber; both are 1/2 OCV against other targets.
     These OCV and DCV modifiers for Grabbing and being Grabbed end
     immediately when the victim breaks free or is released."

FOUR EFFECTS, THREE SHAPES. Two factors, one delta, and one deliberate
no-op:

  * 1/2 DCV, both men          -- factor, and it does not care who is
                                  attacking; a held man is easier for
                                  ANYONE to hit
  * 1/2 OCV against others     -- factor, third parties only
  * full OCV grabber -> victim -- stated, so no later halving creeps in
  * -3 OCV victim -> grabber   -- delta

THE FACTORS ARE 0.5 AND 1.0 AND NOTHING ELSE. `cv_modifiers.apply_cv_factor`
is 6E2 p.39's halving and refuses any other value, which is the check
that keeps a "reasonable" 0.75 out of the rules.

THIS MODULE HOLDS NO STATE. It is handed a reader --- anything answering
`grabbed_by(id)` and `is_grabbing(id)` --- so the same arithmetic serves
a live session and a test double, and so the fold that knows who is
holding whom stays in one place (`actions.grab.Grab.is_grabbed`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

#: 6E2 p.39's single halving, the only factor this file ever produces.
_HALF = 0.5
_NONE = 1.0

#: Western Hero p.104: "the victim is -3 OCV against the Grabber".
_VICTIM_OCV_VS_GRABBER = -3


class HoldReader(Protocol):
    """Who is holding whom. Implemented by `session_holds`."""

    def grabbed_by(self, combatant_id: str) -> str | None: ...
    def is_grabbing(self, combatant_id: str) -> bool: ...
    #: Everyone the reader can speak about. `melee_cover` needs it to ask
    #: the REVERSE question -- who is this man holding -- which
    #: `grabbed_by` alone cannot answer.
    def combatant_ids(self) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class GrabCV:
    """One attacker's CV against one target, given who is in a hold."""

    ocv_factor: float = _NONE
    dcv_factor: float = _NONE
    ocv_delta: int = 0

    @property
    def applies(self) -> bool:
        return (self.ocv_factor, self.dcv_factor, self.ocv_delta) != (
            _NONE, _NONE, 0)


def grab_cv(holds: HoldReader, *, attacker: str, target: str) -> GrabCV:
    """The Grab's CV effects for this attacker against this target."""
    target_held = holds.grabbed_by(target) is not None
    target_holding = holds.is_grabbing(target)
    # A HELD MAN IS EASIER FOR ANYONE TO HIT, and so is the man holding
    # him. This is the half that makes a Grab worth doing to somebody a
    # third man wants to shoot -- and the half that makes holding on a
    # commitment rather than a free action.
    dcv = _HALF if (target_held or target_holding) else _NONE

    attacker_grabber_of_target = holds.grabbed_by(target) == attacker
    attacker_held_by_target = holds.grabbed_by(attacker) == target

    if attacker_grabber_of_target:
        # "The Grabber is full OCV against the victim." Stated rather
        # than left to the default so a later halving cannot creep in.
        return GrabCV(ocv_factor=_NONE, dcv_factor=dcv, ocv_delta=0)
    if attacker_held_by_target:
        return GrabCV(ocv_factor=_NONE, dcv_factor=dcv,
                      ocv_delta=_VICTIM_OCV_VS_GRABBER)

    attacker_in_a_hold = (
        holds.grabbed_by(attacker) is not None or holds.is_grabbing(attacker))
    # "both are 1/2 OCV against other targets" -- the man in a hold is
    # the one penalised, whoever he is shooting at.
    return GrabCV(ocv_factor=_HALF if attacker_in_a_hold else _NONE,
                  dcv_factor=dcv)


class session_holds:                                  # noqa: N801
    """A `HoldReader` over a live fight.

    Reads `Grab.is_grabbed`, which folds the event log --- the single
    answer to "is this man held" that `held_target_ids` and the escape
    offers already use. A second fold here would drift from it.
    """

    def __init__(self, session: Any) -> None:
        self._session = session

    def grabbed_by(self, combatant_id: str) -> str | None:
        from kirby_combat.actions.grab import Grab

        return Grab.is_grabbed(self._session, combatant_id)[1]

    def combatant_ids(self) -> tuple[str, ...]:
        return tuple(getattr(self._session, "combatants", {}))

    def is_grabbing(self, combatant_id: str) -> bool:
        from kirby_combat.actions.grab import Grab

        return any(
            Grab.is_grabbed(self._session, other)[1] == combatant_id
            for other in getattr(self._session, "combatants", {})
        )

#: 6E2 p.45 leaves the figure to the GM --- "based on the number of
#: combatants, how quickly they're moving around, their relative sizes".
#: Its own Behind Cover example on the same page prices a rock that
#: "protects roughly half of Andarra" at -2 OCV, and one man held in
#: front of another is the same shape of obstruction. A judgement, and a
#: grounded one; a campaign that disagrees changes it.
DEFAULT_MELEE_COVER_OCV = -2


@dataclass(frozen=True)
class MeleeCover:
    """The bodies between a shooter and his target (6E2 p.45).

    `other_body` is the man the GM nominates as the alternative target.
    The page makes that a judgement ("The GM decides which combatant is
    the potential target, either randomly, or based on his evaluation of
    the fighters' positions"); with exactly two men in a hold there is
    only one candidate, so the engine can name him without guessing.
    """

    other_body: str | None = None
    ocv_penalty: int = 0

    @property
    def applies(self) -> bool:
        return self.other_body is not None and self.ocv_penalty != 0

    def strays(self, *, missed_by: int) -> bool:
        """Whether this shot may have hit the other man instead.

        "If the roll misses solely as a result of the Behind Cover OCV
        penalty (i.e., it misses by less than or equal to the penalty)".

        A CLOSED BAND, and both ends matter. `missed_by <= 0` is a hit and
        strays nowhere. A miss by MORE than the penalty missed on its own
        merits --- the bodies did not cause it, so they are not in danger.
        """
        if not self.applies:
            return False
        return 0 < missed_by <= abs(self.ocv_penalty)


def melee_cover(holds: HoldReader, *, attacker: str, target: str,
                ocv_penalty: int = DEFAULT_MELEE_COVER_OCV) -> MeleeCover:
    """The other body in the target's melee, if the shooter is outside it.

    NOT FOR THE MEN IN THE HOLD. A grabber shooting his own victim is not
    firing past anybody --- he has hold of him --- and the same is true
    of the victim shooting his grabber. The rule is about a THIRD party
    whose line to one man runs through another.
    """
    partner = holds.grabbed_by(target)
    if partner is None:
        partner = next(
            (other for other in _known(holds)
             if holds.grabbed_by(other) == target), None)
    if partner is None or attacker in (target, partner):
        return MeleeCover()
    return MeleeCover(other_body=partner, ocv_penalty=ocv_penalty)


def _known(holds: HoldReader) -> tuple[str, ...]:
    """Every combatant the reader can speak about.

    Part of `HoldReader` because `melee_cover` cannot work without it:
    `grabbed_by` answers "who holds this man" and the reverse question
    --- "whom does this man hold" --- needs a roster to scan.
    """
    return tuple(getattr(holds, "combatant_ids", lambda: ())())


def stray_ocv(*, base_ocv: int, effective_ocv: int) -> int:
    """The OCV for the second roll (6E2 p.45).

    "using only his base OCV (no bonuses from Combat Skill Levels,
    Combat Maneuvers, or the like apply)" --- so the whole modified
    figure is discarded, whether it was better than base or worse. A
    marksman gets no help hitting the man he was trying NOT to hit, and
    a man shooting uphill in the dark gets no extra excuse either.

    `effective_ocv` is taken and ignored on purpose: a caller reading
    this signature is told, in one line, that the modified value has no
    say.
    """
    return int(base_ocv)
