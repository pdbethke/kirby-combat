""""Close and strike" has to be able to close.

Power Lad is melee-only. The last Cowboy stands off at range. Neither
does anything to the other until the stalemate guard fires --- and
`close_and_strike` is in the catalogue, is APPLICABLE to him, and never
runs.

Its plan has one step, `kind="attack"`. Attack offers are gated by reach,
so when the enemy is not within reach there is no attack on the menu, the
chooser finds nothing matching and falls through. The tactic can strike
and cannot close, which is half its name.

`move_strike` is the engine's word for closing and hitting in one action
--- Power Lad used it to kill five men earlier in the same fight. So the
plan names it first and the plain attack second, and the chooser tries a
plan's steps IN ORDER rather than reading only the first.

That ordering matters beyond this tactic: a plan is a sequence of
preferences, and reading one step of it threw away what every other step
said. It is the same defect as the chooser discarding `target_id` --- a
field written by sixteen tactics and read by none.
"""
from __future__ import annotations

from conftest import blast, fighter               # tests/loop/conftest.py
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.chooser import PhaseSituation, TacticChooser
from kirby_combat.models import AttackPower
from kirby_combat.side import Side
from kirby_combat.tactics.base import Plan, PlanStep, Situation
from kirby_combat.tactics.library import all_tactics


def _claws(id_="lad"):
    c = fighter(id_, side=Side.solo(id_), armed=False)
    c.attacks.append(AttackPower(
        xmlid="HKA", name="Rending", damage_dice=6, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=0.0, uses_str=True, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=False, reach_m=1.0,
        source_id="lad-hka",
    ))
    return c


def _tactic():
    return next(t for t in all_tactics() if t.name == "close_and_strike")


def _situation():
    return Situation(actor=_claws(), allies=[],
                     enemies=[fighter("billy", side=Side.named("cow"))],
                     current_segment=12, turn=1)


def test_the_plan_closes_before_it_strikes():
    steps = _tactic().execute(_situation()).steps
    assert steps[0].kind == "move_strike", (
        "a melee fighter whose enemy is at range must be able to close"
    )


def test_it_still_names_the_plain_attack_as_well():
    """When he is already in reach, closing is not on the menu and the
    strike is."""
    kinds = [s.kind for s in _tactic().execute(_situation()).steps]
    assert "attack" in kinds


def test_it_can_just_close_when_the_gap_is_too_wide_to_close_and_hit():
    """Measured at the O.K. Corral. Power Lad's claws were ON, he HAD the
    attack, and the nearest Cowboy stood 7.8m away against his 8m run ---
    so `attack` was gated by reach (1m) and `move_strike` by the HALF move
    a strike leaves him (4m). Both correctly. His menu held four `move`
    offers and nothing else that touched anybody, no tactic matched, and
    the fallback aimed thirty-eight times.

    A plan that can close-and-hit or hit, but cannot simply WALK, cannot
    start a fight it is not already in.
    """
    kinds = [s.kind for s in _tactic().execute(_situation()).steps]
    assert "move" in kinds
    assert kinds.index("move") > kinds.index("attack"), (
        "walking is the last resort, not the first choice"
    )


# ---- the chooser must read past step one ----

class _TwoStep:
    name = "two_step"
    priority = 999
    basis = None
    narrative_summary = "close, then hit"

    def applicable(self, situation) -> bool:
        return True

    def execute(self, situation) -> Plan:
        return Plan(tactic_name=self.name, rationale="close then hit",
                    steps=[PlanStep(kind="move_strike", target_id="billy"),
                           PlanStep(kind="attack", target_id="billy")])


def _choose(menu):
    from kirby_combat.loop import chooser as chooser_module

    situation = PhaseSituation(
        actor=_claws(), menu=menu,
        enemies=[fighter("billy", side=Side.named("cow"))],
        allies=[], segment=12, turn=1)
    real = chooser_module.tactics_for
    chooser_module.tactics_for = lambda s: [_TwoStep()]
    try:
        return TacticChooser().choose(situation)
    finally:
        chooser_module.tactics_for = real


def _offer(kind, target="billy"):
    return LegalAction(action_id=f"{kind}:{target}:src", kind=kind,
                       target_id=target, power_xmlid="HKA",
                       power_name="Rending", summary=kind)


def test_the_first_step_wins_when_it_is_on_the_menu():
    assert _choose([_offer("attack"), _offer("move_strike")]) == "move_strike:billy:src"


def test_the_second_step_is_used_when_the_first_is_not_offered():
    """He is already in reach: closing is not on the menu, hitting is.

    A DECOY SITS FIRST ON THE MENU on purpose. Reading only step one
    falls through to the fallback, which takes menu[0] --- so without the
    decoy this test would pass on the broken behaviour, which is how the
    first draft of it passed. `dodge` is what the fallback would take.
    """
    chosen = _choose([_offer("dodge", target=None), _offer("attack")])
    assert chosen == "attack:billy:src", (
        "fell through to the fallback instead of reading the plan's "
        "second step"
    )
