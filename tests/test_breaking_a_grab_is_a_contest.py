"""Breaking a Grab is a dice contest, not a comparison of STR.

`Grab.escape` decided it with `escaper_str > grabber_str` --- a raw
comparison, so a STR 20 man ALWAYS escaped a STR 10 man and a STR 10 man
NEVER escaped a STR 11 one. Two books say otherwise.

6E2 p.66:

    "When a Grabbed character tries to escape from his captor, both
     characters roll 1d6 for each 5 STR they have and count the Normal
     Damage BODY. If the Grabbed character's total is higher, he escapes;
     if the Grabber's total is higher or the rolls tie, the victim
     remains Grabbed. Trying to break out of a Grab does no damage to
     either character."

Western Hero p.104, the genre book for this benchmark, adds the margin:

    "If the victim rolls more BODY damage than the grabber, then they
     break free but may take no other actions. If the victim rolls double
     the damage of the grabber, then the escape took no time and the
     victim has their full phase to take advantage of."

So the outcome has THREE states, not two, and a weaker man can still get
lucky --- which is the whole reason to roll.

AND `escape_attack` IS CORRECTLY ABSENT for a Grab. "Trying to break out
of a Grab does no damage to either character", and the attack-to-escape
rules on 6E2 p.126 are about an Entangle. The engine's escape ladder
offers `escape_attack` only under `physical_entangle`, which is right,
and this file records that rather than leaving the absence to look like
an oversight.
"""
from __future__ import annotations

import pytest

from kirby_combat.actions.grab import Grab


def test_dice_are_one_per_five_STR():
    """6E2 p.66: "1d6 for each 5 STR"."""
    assert Grab.escape_dice(10) == 2
    assert Grab.escape_dice(20) == 4
    assert Grab.escape_dice(4) == 0


def test_a_weaker_man_can_still_get_lucky():
    """The point of rolling. A raw comparison made this impossible."""
    assert Grab.escape_outcome(escaper_body=5, grabber_body=3) != "held"


def test_the_grabber_wins_ties():
    """"if the Grabber's total is higher or the rolls tie, the victim
    remains Grabbed"."""
    assert Grab.escape_outcome(escaper_body=4, grabber_body=4) == "held"


def test_the_grabber_wins_when_he_rolls_higher():
    assert Grab.escape_outcome(escaper_body=2, grabber_body=6) == "held"


def test_beating_him_frees_you_but_costs_the_phase():
    """Western Hero p.104: "they break free but may take no other
    actions"."""
    assert Grab.escape_outcome(escaper_body=5, grabber_body=4) == "free_spent"


def test_doubling_him_frees_you_with_the_phase_intact():
    """"If the victim rolls double the damage of the grabber, then the
    escape took no time and the victim has their full phase"."""
    assert Grab.escape_outcome(escaper_body=8, grabber_body=4) == "free_acting"


def test_double_of_zero_is_still_a_clean_break():
    """A grabber who rolls no BODY at all has been beaten by any result,
    and `0 >= 2*0` must not make that a failure."""
    assert Grab.escape_outcome(escaper_body=1, grabber_body=0) == "free_acting"


def test_neither_man_is_hurt_by_the_struggle():
    """"This deals no damage to either character." (Western Hero p.104,
    and 6E2 p.66 in the same words.)"""
    assert Grab.escape_deals_damage is False
