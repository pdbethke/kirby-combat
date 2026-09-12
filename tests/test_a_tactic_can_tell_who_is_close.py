"""A tactic can finally tell who is within arm's length.

`disarm_the_armed` was written today and fired ZERO times, and the reason
was not doctrine. `Situation` carried actor, allies, enemies,
complications and skills --- and **no distance of any kind**. A Disarm is
legal only against a man already in reach, so the tactic named the
biggest gun on the field, `TacticChooser` found that man was not on the
menu, and discarded the plan ("Firing the right KIND at the wrong MAN is
worse than falling through"). The tactic had to fall back to naming
nobody and letting `offers[0]` decide.

So every melee tactic in the catalogue has been reasoning blind about the
one fact melee depends on. `close_and_strike` plans [close, strike]
because it cannot ask; `grab_and_throw` gates on STR 30 instead of
distance.

NO RE-DERIVATION. `in_reach` asks `kirby_combat.actions.reach.within_reach`,
the same predicate enumeration uses, so a tactic and the menu cannot
disagree about who is adjacent --- which is exactly the class of
disagreement the enumerator's own comment warns about ("enumeration could
refuse to offer a melee that the RESOLUTION gate would have allowed").

ABSENT DISTANCES MEAN UNKNOWN, NOT FAR. A scene-less fight (most unit
tests, and the tactic catalogue's own suite) has no positions at all, and
a tactic that read "no distance" as "out of reach" would silently stop
firing there. `in_reach` answers True when it does not know, matching
`_melee_gate`'s own scene-less branch.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Situation


class _Man:
    def __init__(self, id: str):
        self.id = id
        self.name = id.title()
        self.attacks = []
        self.current_stun = self.current_body = self.current_end = 20
        self.max_stun = self.max_body = self.max_end = 20


def _situation(**kw) -> Situation:
    return Situation(actor=_Man("wyatt"), allies=[],
                     enemies=[_Man("ike"), _Man("frank")], **kw)


def test_a_man_at_arms_length_is_in_reach():
    s = _situation(distances_m={"ike": 1.0, "frank": 30.0}, reach_m=2.0)
    assert s.in_reach("ike") is True


def test_a_man_across_the_lot_is_not():
    s = _situation(distances_m={"ike": 1.0, "frank": 30.0}, reach_m=2.0)
    assert s.in_reach("frank") is False


def test_reach_is_the_actors_own():
    """A longer reach brings a further man inside it."""
    far = {"frank": 3.0}
    assert _situation(distances_m=far, reach_m=2.0).in_reach("frank") is False
    assert _situation(distances_m=far, reach_m=4.0).in_reach("frank") is True


def test_an_unknown_distance_is_not_treated_as_far():
    """A scene-less fight has no positions. Reading that as "out of
    reach" would silently disable every melee tactic in the catalogue's
    own suite."""
    assert _situation().in_reach("ike") is True
    assert _situation(distances_m={"frank": 30.0}).in_reach("ike") is True


def test_it_agrees_with_the_engines_own_predicate():
    """The menu and a tactic must not disagree about who is adjacent."""
    from kirby_combat.actions.reach import within_reach

    for d in (0.5, 1.0, 1.9, 2.0, 2.1, 8.0):
        s = _situation(distances_m={"ike": d}, reach_m=2.0)
        assert s.in_reach("ike") is within_reach(d, 2.0).in_reach


def test_the_close_enemies_helper_lists_them():
    """A tactic that wants "whoever I can touch" should not have to loop."""
    s = _situation(distances_m={"ike": 1.0, "frank": 30.0}, reach_m=2.0)
    assert [e.id for e in s.enemies_in_reach()] == ["ike"]
