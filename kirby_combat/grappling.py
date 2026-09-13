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

    def is_grabbing(self, combatant_id: str) -> bool:
        from kirby_combat.actions.grab import Grab

        return any(
            Grab.is_grabbed(self._session, other)[1] == combatant_id
            for other in getattr(self._session, "combatants", {})
        )
