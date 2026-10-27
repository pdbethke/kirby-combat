"""Concentrating on a power (the Concentration Limitation, 6E1 p.374-375).

What the book says, in our words:

* A character using a power with Concentration "is at reduced DCV (1/2 or 0,
  depending upon the Limitation's value)", and "must Concentrate not only
  during the Phase in which he activates the power, but until his next
  Phase" --- Instant powers included.
* He is "only dimly aware of nearby events" and "may not move more than 2m
  per Phase, nor may he Dodge or take any other Actions"; bought OBLIVIOUS,
  "completely oblivious to the rest of the world".
* "Concentration is interrupted if he takes any STUN or BODY damage from any
  Attack Power", and the power turns off.
* An Enraged or Berserk man "cannot use any powers that have the Complication
  Concentration" (6E1 p.424).

THE ENGINE READ NONE OF IT: a 0 DCV Concentration Blast cost its owner
nothing in a fight. Now the use is written down (`ConcentrationBegan`) and
folded forward like every other condition:

* DCV: `cv_modifiers` reads `concentrating` as a ½ or 0 factor.
* NO ABORT: "nor may he Dodge" --- `loop/reactions.may_abort` refuses him.
* THE PHASE HE USES IT IN: the power is an Attack Action and ends the Phase
  anyway. What could come BEFORE it is a Half Move, and he "may not move
  more than 2m per Phase": `not_after_moving` takes a Concentration power
  off the second half of a Phase whose first half moved him (RULING: every
  Half Phase movement offer counts as more than 2m; none is offered shorter).
* ENDS: at the start of the next Segment in which he has a Phase (the same
  reading `martial_arts.maneuver_dcv_delta` gives "until his next Phase"),
  or when STUN or BODY damage reaches him.

RULINGS. The EGO Roll to keep concentrating when hurt is "At the GM's
discretion" and is not taken: damage breaks it. OBLIVIOUS changes nothing
further here: the one thing a dimly aware man could still do --- notice
something with a PER Roll at -3 --- is not a decision this engine models,
and both levels already forbid the Abort and every other Action.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable

from kirby_combat.power_modifiers import ConcentrationDCV

if TYPE_CHECKING:
    from kirby_combat.enumeration import LegalAction
    from kirby_combat.session.combat_session import CombatSession


@dataclass(frozen=True)
class Concentrating:
    """He is concentrating on ``power_id`` at ``dcv``."""

    combatant_id: str
    power_id: str
    dcv: ConcentrationDCV
    oblivious: bool


#: Kinds that move him: a Concentration power is not offered after one in the
#: same Phase ("may not move more than 2m per Phase", 6E1 p.374).
MOVING_KINDS = frozenset({"half_move", "move_to_cover", "escape_teleport"})


def spec_of(action: "LegalAction"):
    """The Concentration bought on the power this offer uses, or None."""
    view = getattr(action, "_attack_view", None)
    return getattr(view, "concentration", None) if view is not None else None


def concentrating(session: "CombatSession", combatant_id: str) -> Concentrating | None:
    """Is he concentrating now? Folded forward from the log."""
    from kirby_combat.tables import segments_for_spd

    combatant = session.combatants.get(combatant_id)
    if combatant is None:
        return None
    phases = set(segments_for_spd(int(combatant.combat_stats().spd)))
    live: Concentrating | None = None
    for evt in session.event_log:
        kind = getattr(evt, "kind", None)
        if kind == "ConcentrationBegan" and evt.combatant_id == combatant_id:
            live = Concentrating(
                combatant_id=combatant_id, power_id=evt.power_id,
                dcv=ConcentrationDCV(evt.dcv), oblivious=bool(evt.oblivious),
            )
        elif live is None:
            continue
        elif kind == "SegmentAdvanced" and evt.to_segment in phases:
            live = None
        elif (kind == "VitalsChanged" and evt.combatant_id == combatant_id
              and evt.reason == "damage"
              and (int(evt.stun or 0) < 0 or int(evt.body or 0) < 0)):
            # "interrupted if he takes any STUN or BODY damage" (p.374).
            live = None
    return live


def begin_if_concentrating(session: "CombatSession", combatant_id: str,
                           action: "LegalAction") -> "CombatSession":
    """Write down a Concentration the Action just used, if it had one."""
    from kirby_combat.session.apply import apply_event
    from kirby_combat.session.events import ConcentrationBegan, make_author_engine

    spec = spec_of(action)
    if spec is None:
        return session
    view = action._attack_view
    return apply_event(session, ConcentrationBegan(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(),
        combatant_id=combatant_id,
        power_id=str(getattr(view, "source_id", "") or ""),
        dcv=spec.dcv.value, oblivious=bool(spec.oblivious),
        turn=int(session.timeline.turn), segment=int(session.timeline.segment),
    ))


def without_concentration_powers(menu: Iterable["LegalAction"]) -> list["LegalAction"]:
    """The menu with every Concentration power taken off."""
    return [a for a in menu if spec_of(a) is None]


def not_after_moving(half_kinds: Iterable[str], menu: Iterable["LegalAction"]) -> list["LegalAction"]:
    """No Concentration power in a Phase he has already moved in."""
    if any(kind in MOVING_KINDS for kind in half_kinds):
        return without_concentration_powers(menu)
    return list(menu)
