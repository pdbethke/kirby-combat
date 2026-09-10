"""Bleeding, and the two separate rules people mean by the word.

**BLEEDING TO DEATH (6E2 p.109, not optional).** "A character at or below
0 BODY is dying. He loses 1 BODY each Turn (at the end of Segment 12) ...
Death occurs when, either due to attacks or 'bleeding to death,' the
character has lost twice his original BODY."

The end of Segment 12 is the same hook the free Post-Segment 12 Recovery
already fires on (6E2 p.131) and that hook only ever handed STUN back, so
before this a dying man lay at -2 BODY for the rest of the fight and
never reached Death by attrition. He also could not be saved, because
nothing could stabilize a condition that was not deteriorating.

**THE OPTIONAL BLEEDING RULES (6E2 p.115).** "Whenever a character loses
BODY, he will Bleed, thus losing STUN and occasionally some extra BODY."
Dice per Turn come from BODY LOST, rolled on Segment 1. "Whenever the
character rolls a six on any of the dice, he loses an additional 1 BODY
... the maximum BODY lost from bleeding is 1 BODY per Turn, even if
several sixes are rolled." Blunt or Normal Damage is "-1 level on the
Bleeding table".

These are OPT-IN by the book's own framing --- "In situations where a
character can get immediate medical care, there's no need to use the
Bleeding rules" --- so the template gates them and a superheroic game
that never wanted them is unchanged. A gunfight is the case they were
written for.

**PARAMEDICS STOPS BOTH**, by two different rolls, which is why both live
here rather than one being folded into the other:

  * p.109, stabilizing the dying: "Another character can stabilize a
    character at 0 or negative BODY with a successful Paramedics roll (at
    -1 for every negative 2 BODY). This doesn't give the wounded
    character back any BODY, it just stabilizes his condition so he
    doesn't lose any more BODY."
  * p.115, stopping a bleeding wound: "Characters with Paramedics (even
    just the Everyman 8- roll) may attempt to stop Bleeding. Appropriate
    tools ... can add up to +3."

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from dataclasses import dataclass

#: p.109. One BODY per Turn, at the end of Segment 12.
BLEED_OUT_BODY_PER_TURN = 1

#: p.115. A six on any die costs a BODY, and the total is capped at one
#: "even if several sixes are rolled".
BLEEDING_BODY_CAP_PER_TURN = 1
BLEEDING_SIX = 6

#: p.115. Everyman Paramedics, which anybody has.
EVERYMAN_PARAMEDICS = 8

#: p.109. "-1 for every negative 2 BODY".
STABILIZE_PENALTY_PER_BODY = 2


@dataclass(frozen=True)
class BleedingBand:
    """One row of p.115's Bleeding Table."""

    max_body_lost: int | None       # None = the open-ended top row
    dice: int
    stop_range: tuple[int, int]

    def covers(self, body_lost: int) -> bool:
        return self.max_body_lost is None or body_lost <= self.max_body_lost


#: p.115's Bleeding Table, in order. Read by band, never computed: the
#: dice column is BODY-lost/5 rounded up only by coincidence, and the
#: Stop Bleeding column follows no formula at all.
BLEEDING_TABLE: tuple[BleedingBand, ...] = (
    BleedingBand(5, 1, (1, 1)),
    BleedingBand(10, 2, (2, 5)),
    BleedingBand(15, 3, (3, 9)),
    BleedingBand(20, 4, (4, 13)),
    BleedingBand(25, 5, (5, 17)),
    BleedingBand(None, 6, (6, 21)),
)


@dataclass(frozen=True)
class BleedingLoss:
    """What one Turn of Bleeding took."""

    stun_lost: int
    body_lost: int
    rolled: tuple[int, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.stun_lost or self.body_lost)


def _band_index(body_lost: int) -> int | None:
    """Which row of the table this wound sits on, or None for no wound."""
    if body_lost <= 0:
        return None
    for i, band in enumerate(BLEEDING_TABLE):
        if band.covers(body_lost):
            return i
    return len(BLEEDING_TABLE) - 1


def bleeding_dice(body_lost: int, *, killing: bool = True) -> int:
    """Dice of STUN per Turn for a wound of this size (6E2 p.115).

    ``killing=False`` applies the page's blunt-weapon clause: "Blunt
    weapons or Normal Damage (from any kind of attack) are less likely to
    induce Bleeding. Such damage is considered to be -1 level on the
    Bleeding table. Thus, a character who has taken up to 5 BODY from
    only Normal Damage will not bleed" --- which is the shift falling off
    the bottom of the table, not a zero written in as a special case.
    """
    index = _band_index(body_lost)
    if index is None:
        return 0
    if not killing:
        index -= 1
    if index < 0:
        return 0
    return BLEEDING_TABLE[index].dice


def bleeding_result(rolled) -> BleedingLoss:
    """STUN and BODY lost from one Turn's Bleeding dice.

    Takes the FACES, not a count, so the caller owns the roller and this
    stays a pure reading of the rule --- and so the audit can quote the
    dice that cost a man the extra BODY.
    """
    faces = tuple(int(face) for face in rolled)
    body = (BLEEDING_BODY_CAP_PER_TURN
            if any(face >= BLEEDING_SIX for face in faces) else 0)
    return BleedingLoss(stun_lost=sum(faces), body_lost=body, rolled=faces)


def stops_bleeding(*, total: int, body_lost: int, killing: bool = True) -> bool:
    """Whether this Turn's Bleeding roll stopped of its own accord.

    Only meaningful for a character who qualified: p.115 requires he "must
    be unconscious or resting for a full Turn --- he cannot engage in any
    type of combat or perform any Action which takes a Half Phase or Full
    Phase in any Segment of that Turn". That is a fact about the Turn,
    which the caller knows and this function does not.
    """
    index = _band_index(body_lost)
    if index is None:
        return False
    if not killing:
        index -= 1
    if index < 0:
        return False
    low, high = BLEEDING_TABLE[index].stop_range
    return low <= total <= high


def bleed_out_body(*, current_body: int) -> int:
    """BODY lost this Turn to bleeding to death (6E2 p.109).

    Zero above 0 BODY: p.109's bleed-out is for the DYING specifically,
    and an ordinary wound bleeding STUN is the separate optional rule
    above. "A foe with positive BODY never bleeds (unless you use the
    optional Bleeding rules)" --- p.122, saying the same thing from the
    other side.
    """
    return BLEED_OUT_BODY_PER_TURN if current_body <= 0 else 0


def stabilize_target(*, paramedics_roll: int, current_body: int,
                     circumstances: int = 0) -> int:
    """The number to make to stabilize a dying character (6E2 p.109).

    "at -1 for every negative 2 BODY" --- so -1 at -2, -2 at -4, and
    nothing extra at 0 or -1. ``circumstances`` is the page's +1 to +3 for
    good care and -1 to -3 for dirt and cold, passed in because it is a
    judgement and not a table.

    Returns the modified target; the caller rolls 3d6 against it. A
    success does NOT restore BODY --- "it just stabilizes his condition so
    he doesn't lose any more BODY".
    """
    below = max(0, -int(current_body))
    return int(paramedics_roll) - (below // STABILIZE_PENALTY_PER_BODY) + int(circumstances)


def stop_bleeding_target(*, paramedics_roll: int, tools: int = 0) -> int:
    """The number to make to stop a bleeding wound (6E2 p.115).

    "Appropriate tools (bandages, pressure packs, antiseptics) can add up
    to +3 to the roll, as can taking additional time. Extremely poor
    conditions or medical techniques ... may warrant a penalty (-1 to
    -3)." Clamped to that stated range rather than trusting a caller.
    """
    return int(paramedics_roll) + max(-3, min(3, int(tools)))


def reopen_target(*, dice: int, made_by: int = 0) -> int:
    """When a stopped wound reopens on exertion (6E2 p.115).

    "If the GM rolls less than (9 + (number of dice character would
    Bleed) - (amount Paramedics roll was made by, if Paramedics was used
    to stop the Bleeding)), the wound reopens". Checked on Segment 1 when
    the character used STR or made a Full Move in the previous Turn.
    """
    return 9 + int(dice) - int(made_by)
