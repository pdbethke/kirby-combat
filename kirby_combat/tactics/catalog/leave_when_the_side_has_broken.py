"""Go, when the side has gone.

The fast signal the catalogue never had. `break_off_when_nothing_works`
reads landed blows, which at OCV 5 against DCV 6 accumulate far slower
than a monster kills --- at the O.K. Corral the Earps reached its
threshold only near the end, by which time Power Lad had killed most of
them. They died faster than they could learn.

Casualties are what actually breaks a group. Watching half your side torn
apart in two Turns is not evidence to be weighed; it is the moment you
leave.

MORALE IS A SIDE'S, NOT A MAN'S --- HERO gives an individual no morale
stat because PRE is the stat (6E2 p.140). `kirby_combat.morale` derives
the side's tier from casualties and futility, using the FRESH / STEADY /
SHAKEN / ROUTING / BROKEN vocabulary `masscombat` already defines.

THIS IS THE ONE PLACE MORALE COMPELS. Everything else it touches should
be a fact tactics weigh --- a doctrine layer overruled by a number is not
a doctrine layer. But ROUTING and BROKEN are not a mood to be weighed
against the odds; a side that has genuinely broken is not choosing, which
is why this sits above every other way of leaving.

AND WHO STAYS IS THE INTERESTING HALF. The side breaks; which men break
with it depends on who they are. A fighter with Overconfidence cannot
conceive of losing and is still standing there when everyone around him
has gone.
"""
from __future__ import annotations

from kirby_combat.masscombat import UnitMorale
from kirby_combat.morale import holds_fast, side_morale
from kirby_combat.side import Side
from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register

#: The tiers that compel rather than advise.
BROKEN_TIERS = (UnitMorale.ROUTING, UnitMorale.BROKEN)


@register
class LeaveWhenTheSideHasBroken(Tactic):
    name = "leave_when_the_side_has_broken"
    basis = Basis(
        judgement="a side that has lost half its men in two Turns is not "
                  "weighing its options, and the ones still standing go",
    )
    #: Above `withdraw_when_outmatched` (54), which is one man deciding he
    #: has nothing to fight with. This is the side deciding for him.
    priority = 56
    narrative_summary = (
        "Half your side is down and you are still here. This is lost -- "
        "not going badly, lost. Get clear while you can still walk."
    )

    @staticmethod
    def _side_of(situation: Situation) -> list:
        """Everyone who came to this fight on the actor's side, THE DEAD
        INCLUDED.

        Off the session rather than `allies`, which holds only who is
        still standing: a side of four that has lost two is not a side of
        two that has lost nobody, and counting survivors alone would say
        exactly that -- the worse a side is beaten, the better its morale
        would read.
        """
        session = situation.session
        if session is None:
            return []
        mine = Side.of(situation.actor)
        return [c for c in getattr(session, "combatants", {}).values()
                if Side.of(c) == mine]

    def applicable(self, situation: Situation) -> bool:
        if situation.session is None:
            return False
        if holds_fast(situation.actor):
            return False
        side = self._side_of(situation)
        if not side:
            return False
        return side_morale(situation.session, side) in BROKEN_TIERS

    def execute(self, situation: Situation) -> Plan:
        side = self._side_of(situation)
        morale = side_morale(situation.session, side)
        down = sum(1 for m in side
                   if getattr(m, "is_ko", False)
                   or getattr(getattr(m, "state", None), "current_body", 1) <= 0)
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"{down} of {len(side)} down; the side is {morale.value}. "
                f"Nothing this fighter does next changes that, and staying "
                f"costs one more man."
            ),
            steps=[
                PlanStep(
                    kind="disengage",
                    notes="Break off and get clear. The side has broken.",
                ),
            ],
            expected_outcome=(
                "The survivors leave the field rather than being killed one "
                "at a time in a fight already decided."
            ),
        )
