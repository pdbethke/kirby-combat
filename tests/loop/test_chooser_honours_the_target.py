"""Doctrine names a victim, and the chooser used to ignore it.

`PlanStep.target_id` has existed as long as `Plan` has, and SIXTEEN of
the catalogue's twenty-two tactics set it. `TacticChooser` read
`plan.steps[0].kind` and nothing else, then took `offers[0]` --- the
first offer of that kind IN MENU ORDER. Menu order is
(power x enemy) in enumeration order, which is roster order. So the
target was whoever happened to be listed first, for every fight this
engine has ever run.

`coordinated_focus_fire` is the sharpest example: a tactic whose entire
purpose is getting a side to concentrate on one man, which could never
once have worked.

Found at the O.K. Corral with Power Lad in it. He killed seven men and
was shot at TWICE in twenty-five Phases, and it was not cowardice or
bad judgement --- he was appended to the roster last, so he was offer
#5 of 5 for everyone, every Phase.

Same shape as three other defects this week: computed, correct, and
delivered nowhere. `compute_cover_level` had one caller. Every tactic's
`narrative_summary` was written for a reader that never saw it.

WHEN THE NAMED TARGET IS NOT ON THE MENU, the tactic is SKIPPED rather
than fired at somebody else. That is this class's stated doctrine --- "a
recommendation absent from the menu is skipped rather than forced" ---
and firing the right kind at the wrong man is worse than falling through
to the next tactic, because it looks like a decision.
"""
from __future__ import annotations

from conftest import blast, fighter              # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.chooser import PhaseSituation, TacticChooser
from kirby_combat.side import Side
from kirby_combat.tactics.base import Plan, PlanStep


class _Doctrine:
    """A tactic that names one man. Stands in for the sixteen that do."""

    name = "shoot_the_monster"
    priority = 999
    basis = None
    narrative_summary = "Shoot the one who is killing everybody."

    def __init__(self, target_id: str | None) -> None:
        self._target = target_id

    def applicable(self, situation) -> bool:
        return True

    def execute(self, situation) -> Plan:
        return Plan(tactic_name=self.name, rationale="the one killing everybody",
                    steps=[PlanStep(kind="attack", target_id=self._target)])


def _menu(*target_ids) -> list[LegalAction]:
    return [LegalAction(action_id=f"attack:{t}:src1", kind="attack",
                        target_id=t, power_xmlid="ENERGYBLAST",
                        power_name="Blast", summary=f"shoot {t}")
            for t in target_ids]


def _situation(menu):
    actor = fighter("shooter", side=Side.named("law"))
    enemies = [fighter(a.target_id, side=Side.named("cow")) for a in menu]
    return PhaseSituation(actor=actor, menu=menu, enemies=enemies,
                          allies=[], segment=12, turn=1)


def _choose(menu, tactic):
    chooser = TacticChooser()
    situation = _situation(menu)
    # Drive the one tactic under test rather than the whole catalogue, so
    # this measures the chooser and not the catalogue's priority order.
    from kirby_combat.loop import chooser as chooser_module
    real = chooser_module.tactics_for
    chooser_module.tactics_for = lambda s: [tactic]
    try:
        return chooser.choose(situation)
    finally:
        chooser_module.tactics_for = real


def test_the_named_target_is_the_one_attacked():
    """Not offer #1. The monster is last in the roster and must still be
    the one shot."""
    menu = _menu("wyatt", "virgil", "power_lad")
    assert _choose(menu, _Doctrine("power_lad")) == "attack:power_lad:src1"


def test_a_tactic_that_names_nobody_still_takes_the_first_offer():
    """Guards the guard: six of the twenty-two name no one, and their
    behaviour must not change."""
    menu = _menu("wyatt", "virgil", "power_lad")
    assert _choose(menu, _Doctrine(None)) == "attack:wyatt:src1"


def test_a_named_target_who_is_not_on_the_menu_falls_through():
    """Legality wins over doctrine, as this class already says. Firing
    the right KIND at the wrong MAN would look like a decision."""
    menu = _menu("wyatt", "virgil")
    # The fallback is FirstLegalChooser, so falling through lands on #1 --
    # but it must arrive there by falling through, not by pretending the
    # named target was matched.
    assert _choose(menu, _Doctrine("power_lad")) == "attack:wyatt:src1"
