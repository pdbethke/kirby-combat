"""0 BODY is not Knocked Out. It is DYING, and it gets worse each Turn.

6E2 p.109: "A character at or below 0 BODY is dying. He loses 1 BODY each
Turn (at the end of Segment 12). This is usually referred to as 'bleeding
to death' ... Death occurs when, either due to attacks or 'bleeding to
death,' the character has lost twice his original BODY (i.e., when he
reaches a negative BODY score equal to his starting positive BODY)."

And 6E2 p.105 is emphatic that dying is not unconsciousness: "A character
can have 0 BODY or negative BODY and still have lots of STUN -- he's
dying, but awake and active."

WHAT THE ENGINE HAD. Death was right: `determine_status_changes` returns
"Dead" on `body_after <= -max_body`, which is the rule exactly. Dying did
not exist -- the word appeared nowhere in the engine -- so:

  * a man at 0 BODY was reported as "Knocked Out" and nothing else, which
    is what a Krackle replay showed on its status card; and
  * nobody ever bled. The Post-Segment 12 hook that applies the free
    Recovery (6E2 p.131) is once per Turn and is exactly where p.109 puts
    the loss, and it only ever gave STUN back. A dying man could lie at
    -2 BODY for the rest of the fight and never reach Death by attrition.

`is_down` folds "STUN <= 0 or BODY <= 0" into one boolean, which is right
for "can he keep fighting" and wrong as a description: it is why the two
distinct conditions were reported as one.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from kirby_combat.resolution.status import determine_status_changes


def _statuses(*, body_after: int, max_body: int = 10, stun_after: int = 20):
    return determine_status_changes(
        stun_before=25, stun_after=stun_after,
        body_before=max_body, body_after=body_after,
        con=20, max_body=max_body,
    )


def test_zero_body_is_dying():
    assert "Dying" in _statuses(body_after=0)


def test_below_zero_body_is_dying():
    assert "Dying" in _statuses(body_after=-4)


def test_positive_body_is_not_dying():
    assert "Dying" not in _statuses(body_after=1)


def test_dying_does_not_require_being_unconscious():
    """p.105: "dying, but awake and active". A man on his feet with a
    hole in him is both, and the card has to be able to say so."""
    out = _statuses(body_after=-1, stun_after=18)
    assert "Dying" in out
    assert "Knocked Out" not in out


def test_dead_is_not_also_reported_as_dying():
    """Past the threshold there is nothing left to bleed out. Reporting
    both would put two mutually exclusive words on one status card."""
    out = _statuses(body_after=-10, max_body=10)
    assert "Dead" in out
    assert "Dying" not in out


def test_the_death_threshold_is_still_the_starting_body():
    """p.109's own example: 10 BODY dies at -10; 8 BODY dies at -8."""
    assert "Dead" in _statuses(body_after=-8, max_body=8)
    assert "Dead" not in _statuses(body_after=-7, max_body=8)
