"""The page says what the SIDE is trying to do, not just the man.

PeterB: "maybe we need a model for goals - team goals and individual
goals", and then, concretely, "virgil's goal should be kill the cowboys"
-- "not shoot buildings".

HALF OF THAT ALREADY EXISTED. Individual goals are Psychological
Complications, which the Brief now renders under "What drives you". The
other half did not: a fighter could read his own code of honour and had
no way to learn that the Earps were in that lot to DISARM the Cowboys
rather than to kill them or to demolish Fly's Boarding House.

WHY THIS IS A STRING AND NOT A TEAM. kirby-combat must never import
kirby-campaign -- the bridge from a standing team to a fight's sides is
deliberately "a plain `side: str`", and `Side.team_id` is documented as
an opaque back-reference that is "never dereferenced here". An objective
is the same shape: the campaign layer knows what the Earps want, writes
it down when it builds the sides, and the engine renders it without ever
asking what a Team is. Holding a real Team here would drag the campaign
entity layer behind every fight.

AND IT DOES NOT SPLIT A SIDE. Two references to the same side must
compare equal, which is why `team_id` is `compare=False`; an objective is
display and reference in exactly the same way, and gets the same
treatment. A fight whose two halves disagree about the wording of a goal
is still one fight.
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
    hero = None

    def __init__(self, side=None):
        self.side = side

    class state:
        current_stun = current_body = current_end = 20

    def combat_stats(self):
        return _Stats()


def _page(actor):
    menu = [LegalAction(action_id="dodge", kind="dodge", target_id=None,
                        power_xmlid=None, power_name=None, summary="Dodge")]
    return Brief(PhaseSituation(actor=actor, menu=menu, segment=12, turn=1)).render()


def test_the_page_states_the_side_objective():
    side = Side.named("Earps", objective="Disarm the Cowboys and arrest them.")
    assert "Disarm the Cowboys" in _page(_Actor(side))


def test_a_side_with_no_objective_gets_no_empty_heading():
    """Most fights are two nameless sides shooting at each other, and a
    heading over nothing is noise on a page paid for by the token."""
    page = _page(_Actor(Side.named("Earps")))
    assert "trying to do" not in page.casefold()


def test_an_objective_does_not_split_a_side():
    """Two references to one side must compare equal -- the same reason
    `team_id` is `compare=False`. A fight whose halves word the goal
    differently is still one fight."""
    a = Side.named("Earps", objective="Disarm them.")
    b = Side.named("Earps")
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_it_survives_a_team_id_alongside_it():
    side = Side.named("Earps", team_id="team-earp", objective="Disarm them.")
    assert side.team_id == "team-earp"
    assert side.objective == "Disarm them."
