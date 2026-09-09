"""The chooser records why it chose.

`TacticChooser` computes a `Plan` for every decision --- carrying the
tactic's name, its `rationale`, and its `Basis`, which is either a
rulebook citation or a stated judgement --- and throws ALL of it away,
keeping the action id. So a fight's record says what happened and never
why, and the doctrine layer is unmeasurable: you cannot ask which tactics
fire, which never fire, or which correlate with winning.

Measured across twelve fights by attributing picks to the first tactic
whose plan matched the chosen KIND: five of twenty-four appeared to drive
decisions and `fight_from_cover` took 78% of them. That attribution is a
GUESS --- several tactics emit `attack`, and the first match wins --- which
is exactly why the chooser has to say so itself.

`ModelChooser` already keeps `picks` for the same reason: "a fight driven
by a model is worth being able to explain afterwards". A fight driven by
doctrine is worth the same, and doctrine is the half that can actually
cite a page.

Fourteenth thing found this week that was computed, correct and delivered
nowhere.
"""
from __future__ import annotations

from conftest import blast, fighter               # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.chooser import PhaseSituation, TacticChooser
from kirby_combat.side import Side
from kirby_combat.tactics.base import Basis, Plan, PlanStep


class _Doctrine:
    name = "shoot_the_monster"
    priority = 999
    basis = Basis(judgement="the one killing everybody is the problem")
    narrative_summary = "Shoot the one who is killing everybody."

    def applicable(self, situation) -> bool:
        return True

    def execute(self, situation) -> Plan:
        return Plan(tactic_name=self.name,
                    rationale="he has killed two men already",
                    steps=[PlanStep(kind="attack", target_id="power_lad")])


def _offer(target):
    return LegalAction(action_id=f"attack:{target}:src", kind="attack",
                       target_id=target, power_xmlid="ENERGYBLAST",
                       power_name="Blast", summary="shoot")


def _choose(menu, tactic=None):
    from kirby_combat.loop import chooser as chooser_module

    chooser = TacticChooser()
    situation = PhaseSituation(
        actor=fighter("wyatt", side=Side.named("law")), menu=menu,
        enemies=[fighter("power_lad", side=Side.solo("power_lad"))],
        allies=[], segment=12, turn=1)
    real = chooser_module.tactics_for
    chooser_module.tactics_for = lambda s: ([tactic] if tactic else [])
    try:
        chooser.choose(situation)
    finally:
        chooser_module.tactics_for = real
    return chooser


def test_it_records_the_tactic_that_decided():
    chooser = _choose([_offer("power_lad")], _Doctrine())
    assert chooser.picks[-1].tactic == "shoot_the_monster"


def test_it_records_the_rationale():
    """The sentence the tactic wrote about THIS situation, not its
    permanent description."""
    chooser = _choose([_offer("power_lad")], _Doctrine())
    assert "killed two men" in chooser.picks[-1].rationale


def test_it_records_the_basis():
    """A citation or a stated judgement --- the thing that makes a choice
    arguable with a GM."""
    chooser = _choose([_offer("power_lad")], _Doctrine())
    assert "killing everybody" in chooser.picks[-1].basis


def test_it_records_the_action_it_actually_took():
    chooser = _choose([_offer("power_lad")], _Doctrine())
    assert chooser.picks[-1].action_id == "attack:power_lad:src"


def test_a_decision_with_no_doctrine_says_so():
    """Falling through to the fallback is a decision and not an error ---
    this class says so itself --- but it must be visible as one, or a
    fight driven entirely by the fallback reads as doctrine working."""
    chooser = _choose([_offer("power_lad")], None)
    assert chooser.picks[-1].tactic is None
    assert chooser.picks[-1].fell_back is True


def test_every_phase_is_recorded_in_order():
    from kirby_combat.loop import chooser as chooser_module

    chooser = TacticChooser()
    situation = PhaseSituation(
        actor=fighter("wyatt", side=Side.named("law")),
        menu=[_offer("power_lad")],
        enemies=[fighter("power_lad", side=Side.solo("power_lad"))],
        allies=[], segment=12, turn=1)
    real = chooser_module.tactics_for
    chooser_module.tactics_for = lambda s: [_Doctrine()]
    try:
        chooser.choose(situation)
        chooser.choose(situation)
    finally:
        chooser_module.tactics_for = real
    assert len(chooser.picks) == 2
