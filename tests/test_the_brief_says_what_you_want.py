"""The page says what the fighter is trying to achieve.

A Brief listed the actor, the allies, the enemies, the ground, the
doctrine and the menu, and never once said what the man WANTED. A reader
was handed a complete tactical picture with the motive cut out of it, and
then asked to choose --- so "sensible" could only ever mean "legal".

That is the whole of Virgil Earp shooting the Harwood House. Nothing on
his page said he was a marshal whose business was the Cowboys; the house
was simply the first thing he was allowed to hit.

HERO ALREADY HAS A GOALS MODEL AND IT IS NOT A NEW SUBSYSTEM. Psychological
Complications are what a character will and will not do --- "Code Against
Killing", "Overconfidence", "Protective Of Innocents" --- priced on the
sheet and, per 6E2 p.138, severe enough to be worth Presence Attack dice.
`complications_of` has read them since the loop learned to fill
`Situation.actor_complications`, and exactly two tactics look at them.
The page never showed them to anybody.

SEVERITY IS PART OF THE GOAL. "Code Against Killing (Total)" and a
Moderate reluctance are different instructions, and the book already
grades them on the rungs this renders.

This states and derives nothing: the complications are on the build, the
side is on the combatant. It is the same defect as the terrain section,
which was computed for the rules long before the page that needed it said
a word about the ground.
"""
from __future__ import annotations

from kirby_combat.brief import Brief
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.chooser import PhaseSituation
from kirby_combat.side import Side


class _Stats:
    ocv = dcv = 8
    omcv = dmcv = 5
    max_stun = max_body = max_end = 20
    str_ = con = 15
    dex = ego = int_ = 10
    pre = 15
    spd = 4
    pd = ed = 10
    rpd = red = 2


class _Actor:
    id = "virgil_earp"
    name = "Virgil Earp"
    max_stun = current_stun = 20
    max_body = current_body = 20
    max_end = current_end = 20

    def __init__(self, side=None, complications=()):
        self.side = side
        self.hero = _Hero(complications)

    class state:
        current_stun = current_body = current_end = 20

    def combat_stats(self):
        return _Stats()


class _Hero:
    """The shape `complications_of` actually reads: a build whose
    complications carry the player's text in `input`, and severity in the
    adder string HD writes."""

    def __init__(self, complications):
        self.complications = list(complications)


class _RawComp:
    xmlid = "PSYCHOLOGICALLIMITATION"
    alias = "Psychological Complication"
    notes = ""
    levels = 0
    adders = ()

    def __init__(self, text, adder_string=""):
        self.input = text
        self.adder_string = adder_string


def _comp(text, *, severity=None):
    return _RawComp(
        text,
        # HD writes severity as free text; `_adders_of` parses these words.
        adder_string=(f"Intensity Is {severity.title()}, Situation Is (Common)"
                      if severity else ""),
    )


def _page(actor):
    menu = [LegalAction(action_id="dodge", kind="dodge", target_id=None,
                        power_xmlid=None, power_name=None, summary="Dodge")]
    return Brief(PhaseSituation(actor=actor, menu=menu, segment=12, turn=1)).render()


def test_the_page_names_what_drives_the_fighter():
    page = _page(_Actor(complications=[_comp("Sworn to uphold the law")]))
    assert "Sworn to uphold the law" in page


def test_severity_comes_with_it():
    """A Total code and a Moderate reluctance are different instructions."""
    page = _page(_Actor(complications=[_comp("Code Against Killing",
                                             severity="total")]))
    assert "Code Against Killing" in page
    assert "Total" in page or "TOTAL" in page


def test_a_fighter_with_no_complications_gets_no_empty_heading():
    """Most combatants have none, and a heading over nothing is noise on a
    page that is read by something paying by the token."""
    page = _page(_Actor())
    assert "drives" not in page.casefold()


def test_the_side_is_on_the_page():
    """"Enemies:" says who to fight and never says who you are with. A
    fighter who does not know his own side cannot weigh a goal that
    belongs to it."""
    page = _page(_Actor(side=Side.named("Earps")))
    assert "Earps" in page
