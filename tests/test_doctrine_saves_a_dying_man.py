"""Doctrine lets men bleed to death, and it does not have to.

`stabilize` has been offered 94 times across the western benchmarks and
taken zero times. Measured on the corral, six fights: **31 offers, 29
bleeding ticks, and not one attempt to help.**

The rule is not ambiguous about the stakes (6E2 p.109): a character at 0
or negative BODY is DYING, loses 1 BODY per Turn, and death is inevitable
without intervention. 6E2 p.115 gives the attempt to anybody --- "even
just the Everyman 8- roll" --- and Doc Holliday at this fight carries
PARAMEDICS 11.

So every piece was built and wired: the bleeding rules, the Dying status,
the Paramedics roll, the `stabilize` offer keyed to the ALLY's condition.
The only thing missing was a tactic that ever picks it, which made the
whole feature inert in play --- a rung above "computed, delivered
nowhere": delivered, offered, and never chosen.

PRIORITY. Above `take_cover_when_hurt` (55) and `withdraw_when_outmatched`
(54): a man who will die this Turn without help outranks the actor's own
comfort. Below `exploit_susceptibility` (60), which is about ending the
fight outright.
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


class _Man:
    """An ally or actor as the tactic layer sees one."""

    def __init__(self, id: str, *, body: int = 20, stun: int = 20):
        self.id = id
        self.name = id.title()
        self.current_body = body
        self.current_stun = stun
        self.current_end = 20
        self.max_stun = self.max_body = self.max_end = 20
        self.attacks = []

    def combat_stats(self):
        return _Stats()


def _situation(allies, *, skills=None) -> Situation:
    return Situation(
        actor=_Man("doc_holliday"), allies=allies,
        enemies=[_Man("ike_clanton")],
        actor_skills=dict(skills or {"PARAMEDICS": 11}),
    )


def _tactic():
    from kirby_combat.tactics.catalog.stabilize_the_dying import StabilizeTheDying

    return StabilizeTheDying()


def test_a_dying_ally_makes_the_tactic_apply():
    """0 BODY is DYING, not knocked out (6E2 p.105)."""
    assert _tactic().applicable(_situation([_Man("morgan_earp", body=0)]))


def test_a_bleeding_ally_below_zero_still_applies():
    assert _tactic().applicable(_situation([_Man("morgan_earp", body=-4)]))


def test_healthy_allies_do_not_trigger_it():
    assert not _tactic().applicable(_situation([_Man("wyatt_earp", body=20)]))


def test_a_knocked_out_but_not_dying_ally_does_not_trigger_it():
    """STUN 0 with BODY intact is unconscious, not bleeding out. Spending
    the Phase on Paramedics there wastes it."""
    assert not _tactic().applicable(
        _situation([_Man("wyatt_earp", body=12, stun=0)]))


def test_a_man_with_no_allies_left_has_nobody_to_save():
    assert not _tactic().applicable(_situation([]))


def test_the_plan_names_the_dying_man():
    """A stabilize roll's difficulty depends on WHICH man is bleeding
    (-1 per -2 BODY), so a plan that names no target is unexecutable."""
    plan = _tactic().execute(_situation([
        _Man("wyatt_earp", body=20), _Man("morgan_earp", body=-2),
    ]))
    assert plan.steps
    assert plan.steps[0].kind == "stabilize"
    assert plan.steps[0].target_id == "morgan_earp"


def test_the_worst_off_man_is_chosen_first():
    """Bleeding costs 1 BODY a Turn and death arrives at -BODY, so the
    man nearest it is the one who cannot wait."""
    plan = _tactic().execute(_situation([
        _Man("wyatt_earp", body=-1), _Man("morgan_earp", body=-9),
    ]))
    assert plan.steps[0].target_id == "morgan_earp"


def test_it_is_registered_in_the_catalogue():
    """A tactic nothing can reach is documentation."""
    from kirby_combat.tactics.library import all_tactics

    assert "stabilize_the_dying" in {t.name for t in all_tactics()}
