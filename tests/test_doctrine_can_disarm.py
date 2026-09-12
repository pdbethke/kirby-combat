"""Doctrine could not pursue its own side's stated objective.

The corral's Earps carry this, in the scene file, as `Side.objective`:

    "Disarm the Cowboys and place them under arrest.
     Shoot the men, not the buildings."

and the Cowboys answer it:

    "Do not be disarmed. Fight your way clear of the lot..."

The Brief renders that objective to whoever is deciding. `disarm` is
enumerated, resolvable, and was chosen 3 times by a model that read the
page. And the tactic catalogue had **no disarm entry of any kind** --- 26
tactics and not one of them takes a man's gun --- so the rule-based
chooser could never once do the thing its own side said it was there to
do.

WHY THIS TACTIC DOES NOT READ THE OBJECTIVE. Gating on the prose would
mean parsing it, and this session already declined that once: the
`scenery` grader deliberately compares menus rather than reading
`Side.objective`, because a regex over a GM's sentence is not a rule.
Taking an armed man's weapon is sound doctrine wherever it is legal, so
the tactic states that and lets legality decide --- which is the
catalogue's own contract: "WHEN DOCTRINE AND LEGALITY DISAGREE, LEGALITY
WINS." A Disarm against a man out of reach is simply absent from the
menu, and `TacticChooser` skips the plan.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Situation


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


class _Gun:
    xmlid = "RKA"
    name = "Colt revolver"
    damage_dice = 2
    range_m = 100.0


class _Fists:
    xmlid = "HANDTOHANDATTACK"
    name = "Fists"
    damage_dice = 2
    range_m = 0.0


class _Man:
    def __init__(self, id: str, attacks=(), *, body: int = 20, stun: int = 20):
        self.id = id
        self.name = id.title()
        self.attacks = list(attacks)
        self.current_body = body
        self.current_stun = stun
        self.current_end = 20
        self.max_stun = self.max_body = self.max_end = 20

    def combat_stats(self):
        return _Stats()


def _situation(enemies) -> Situation:
    return Situation(actor=_Man("wyatt_earp", [_Gun()]), allies=[],
                     enemies=enemies)


def _tactic():
    from kirby_combat.tactics.catalog.disarm_the_armed import DisarmTheArmed

    return DisarmTheArmed()


def test_an_armed_enemy_makes_it_apply():
    assert _tactic().applicable(_situation([_Man("ike_clanton", [_Gun()])]))


def test_an_unarmed_man_is_not_worth_disarming():
    """Ike Clanton ran from this fight unarmed. There is nothing to take."""
    assert not _tactic().applicable(_situation([_Man("ike_clanton", [])]))


def test_a_man_with_only_fists_is_not_worth_disarming():
    """A Disarm takes a WEAPON. You cannot disarm a bare hand."""
    assert not _tactic().applicable(_situation([_Man("tom", [_Fists()])]))


def test_a_downed_enemy_is_not_a_target():
    """`Situation.enemies` is documented as living-only and the real
    caller does not filter, which the catalogue's other tactics already
    carry a comment about."""
    assert not _tactic().applicable(
        _situation([_Man("billy", [_Gun()], stun=0)]))


def test_the_plan_deliberately_names_no_victim():
    """A Disarm is legal only against a man already in reach, and the
    tactic layer CANNOT SEE REACH --- `Situation` carries no distance of
    any kind. Naming the biggest gun named a man across the lot, and
    `TacticChooser` discards a plan whose target is not on the menu, so
    the tactic fired zero times. Target-less, the chooser takes the first
    Disarm offer, which is by construction against an adjacent armed man.
    """
    plan = _tactic().execute(_situation([
        _Man("ike_clanton", []), _Man("frank_mclaury", [_Gun()]),
    ]))
    assert plan.steps
    assert plan.steps[0].kind == "disarm"
    assert plan.steps[0].target_id is None


def test_the_rationale_still_names_the_biggest_gun():
    """The reader is told who matters even though the step is not aimed."""
    plan = _tactic().execute(_situation([_Man("frank_mclaury", [_Gun()])]))
    assert "Frank_Mclaury" in plan.rationale or "frank" in plan.rationale.lower()


def test_it_is_registered():
    from kirby_combat.tactics.library import all_tactics

    assert "disarm_the_armed" in {t.name for t in all_tactics()}
