"""A tactic's first step must NAME the action it wants.

THE DEFECT THIS PINS. Four tactics in the catalogue asked for one action
in `kind` and a different one in `notes`:

    PlanStep(kind="move",
             notes="Choose move_to_cover from the action menu...")

`TacticChooser` matches a plan's first step against the menu BY KIND and
takes `by_kind[kind][0]`. It never reads `notes` --- that prose was
written for a chooser that reads text, and against a kind-matching seat
it is a comment.

So a tactic that wanted COVER got whatever the first `move` offer
happened to be. On the O.K. Corral that was "close on the nearest enemy",
from two metres away, every Phase: `fight_from_cover` (priority 40)
outranks `sustained_fire`, so the three ARMED Cowboys walked at Wyatt
Earp for the whole fight and never fired a shot. The Earps won 4-0 and
the result line read like a clean doctrinal victory. It took a
play-by-play to notice that three of the five men on the losing side
never took their guns out.

The fix is not to teach the chooser to read prose. It is for the step to
say what it means --- `move_to_cover` and `attack_construct` are real
kinds. When the wanted kind is absent from the menu the chooser falls
through to the next tactic, which is the right answer: no cover to take
means take the shot instead.
"""
from __future__ import annotations

import re

import pytest

from kirby_combat.enumeration import ALL_ACTION_KINDS
from kirby_combat.models import AttackPower
from kirby_combat.tactics.base import Situation
from kirby_combat.tactics.library import all_tactics

#: Notes may DESCRIBE the step's action; they must not send the reader to
#: a different one. These are the phrasings that did.
_REDIRECT = re.compile(
    r"choose\s+(?:the\s+)?([a-z_]+(?::[a-z_]+)?)\s+"
    r"(?:from the action menu|action)",
    re.IGNORECASE,
)


def _gun(name="Colt", xmlid="RKA", range_m=100.0):
    return AttackPower(
        xmlid=xmlid, name=name, damage_dice=2, half_die=False, plus_one=False,
        damage_type="killing", defense_type="pd", range_m=range_m,
        uses_str=False, str_min=10, armor_piercing=0, penetrating=0,
        increased_stun_mult=0, is_ranged=range_m > 0)


class _Fighter:
    """The least an actor can be and still let every tactic execute."""

    def __init__(self, cid):
        self.id = cid
        self.attacks = [_gun(), _gun("Fists", "STR", 0.0)]
        self.current_stun = 20
        self.max_stun = 30
        self.current_body = 10
        self.max_body = 10
        self.current_end = 20
        self.is_ko = False


def _situation():
    return Situation(
        actor=_Fighter("actor"),
        allies=[_Fighter("ally")],
        enemies=[_Fighter("mark"), _Fighter("other")],
    )


def _plans():
    """Every tactic that can execute, with its plan. A tactic that raises
    on this deliberately-minimal situation is skipped rather than failed
    --- this test is about what the steps SAY, not about coverage."""
    situation = _situation()
    for tactic in all_tactics():
        try:
            yield tactic, tactic.execute(situation)
        except Exception:                                # pragma: no cover
            continue


_PLANS = list(_plans())
_IDS = [t.name for t, _p in _PLANS]


@pytest.mark.parametrize("tactic,plan", _PLANS, ids=_IDS)
def test_no_step_sends_the_reader_to_another_action(tactic, plan):
    for step in plan.steps or []:
        match = _REDIRECT.search(step.notes or "")
        if not match:
            continue
        # NO SPLITTING ON THE COLON. "move:cover" and "attack:construct"
        # are action-ID syntax for ids that never existed, and treating
        # them as "move" and "attack" is exactly the reading that let both
        # slip through: the prefix matched the step's kind, so the step
        # looked consistent while asking for something else.
        assert match.group(1) == step.kind, (
            f"{tactic.name}: step kind is {step.kind!r} but its notes tell "
            f"the reader to choose {match.group(1)!r}. The chooser matches "
            f"on kind and never reads notes, so this step gets an arbitrary "
            f"{step.kind!r} offer instead."
        )


#: Two tactics emit `kind="wait"`, which `ALL_ACTION_KINDS` does not
#: contain and no menu can offer, so both are INERT: they outrank their
#: juniors, fall through every time, and have never once been chosen.
#:
#: NOT FIXED HERE, and not because it is hard. Both mean "hold, then abort
#: when someone swings" --- a two-part intention the plan format cannot
#: express as one kind. Mapping them to the nearest real kinds (`dodge`,
#: `block`) would make them fire, and at priorities 52 and 48, in any
#: fight where the enemy has guns, EVERY fighter would dodge or block
#: every Phase and nobody would shoot. That is the same defect this file
#: is about, moved one tactic over.
#:
#: The real repair is either an abort-aware step kind or a priority pass,
#: and it wants its own change. Listed rather than skipped so the count is
#: visible: two of twenty tactics are dead weight in the ordering.
_INERT_BY_DESIGN_DECISION = {"abort_to_block", "dodge_under_fire"}


@pytest.mark.parametrize("tactic,plan", _PLANS, ids=_IDS)
def test_every_step_kind_is_a_real_action_kind(tactic, plan):
    """A step naming a kind nothing enumerates can never match, so the
    tactic is dead weight in the ordering --- it outranks its juniors and
    then always falls through."""
    if tactic.name in _INERT_BY_DESIGN_DECISION:
        pytest.xfail(f"{tactic.name} emits 'wait', which is not an action "
                     f"kind -- see _INERT_BY_DESIGN_DECISION")
    for step in plan.steps or []:
        assert step.kind in ALL_ACTION_KINDS, (
            f"{tactic.name}: step kind {step.kind!r} is not in "
            f"ALL_ACTION_KINDS, so no menu can ever satisfy it"
        )


def test_the_inert_list_has_not_quietly_grown():
    """An allowlist that absorbs new entries stops being a record of two
    known gaps and becomes permission. Pinned at two."""
    assert _INERT_BY_DESIGN_DECISION == {"abort_to_block", "dodge_under_fire"}


def test_the_catalogue_actually_loaded():
    """Guards the guard: an empty registry would pass everything above."""
    assert len(_PLANS) >= 8
