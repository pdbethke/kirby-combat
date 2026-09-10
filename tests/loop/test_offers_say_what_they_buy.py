"""An offer has to say what taking it is worth.

Measured over six fights each, doctrine and a model reach the SAME three
kinds of sixty-two, spending nine actions in ten on plain `attack`. That
result rules out the chooser: swapping a catalogue for a frontier model
moved the count by one. What is left is the page.

Reading it, the diagnosis is narrower than "offers don't say what they
buy". Most of them do, and say their COSTS well:

    Dodge — +3 DCV until your next phase (full DCV bonus, but no attack)
    Move-By: 2d6N ... Cost: -2 OCV / -2 DCV, 1/3 self-damage

Two things are missing, and they are the two that matter:

**The baseline says the least.** `attack` -- the action taken nine times
in ten -- read "Attack Billy Clanton with Coach gun (3d6K, OCV 7)". No
target number. Every alternative quotes a CV modifier, and a -2 OCV means
nothing without the number it modifies: -2 off a comfortable 14- is a
different decision from -2 off a marginal 9-.

**Hiding never mentions what hiding is FOR.** It read "enemies who can't
perceive you can't target you", which is the small half. The large half
is 6E2 p.52: an attacker they cannot perceive catches them Surprised, at
half DCV -- and `hide` is the only manoeuvre in the game that produces
it. Offered 89 times across six fights and taken zero times by either
chooser, so the whole Surprised path is unreachable in this benchmark
while being fully wired underneath.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

import pytest


def _summaries():
    from examples.the_shootout_we_can_publish import the_fight

    seen: dict[str, str] = {}

    class Peek:
        def choose(self, situation):
            for action in situation.menu:
                seen.setdefault(action.kind, action.summary)
            return situation.menu[0].action_id

    the_fight(59, chooser=Peek())
    return seen


@pytest.fixture(scope="module")
def summaries():
    return _summaries()


class TestTheBaselineOffer:
    def test_an_attack_says_the_number_it_needs(self, summaries):
        """3d6 <= OCV + 11 - DCV. Without it, every CV modifier on every
        other offer is uncomparable."""
        assert "needs" in summaries["attack"], summaries["attack"]

    def test_and_the_number_is_the_engines_own(self, summaries):
        """OCV 7 against Billy Clanton's DCV 4 is 7 + 11 - 4 = 14-."""
        assert "14-" in summaries["attack"], summaries["attack"]

    def test_it_still_says_what_it_hits_with(self, summaries):
        """Adding the number must not cost the damage."""
        assert "3d6K" in summaries["attack"], summaries["attack"]


class TestHiding:
    def test_hiding_says_it_causes_surprise(self, summaries):
        """Case-insensitive: the offer shouts it, and which case it
        shouts in is not the thing under test."""
        assert "surprised" in summaries["hide"].lower(), summaries["hide"]

    def test_and_what_surprise_is_worth(self, summaries):
        """Half DCV is the payoff, and it is the reason to spend a Phase."""
        assert "DCV" in summaries["hide"], summaries["hide"]

    def test_it_still_says_the_cost(self, summaries):
        """It breaks when you attack --- that has to survive the rewrite."""
        assert "attack" in summaries["hide"].lower(), summaries["hide"]
