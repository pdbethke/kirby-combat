"""Stop doing the thing that does not work.

The complement to `withdraw_when_outmatched`, which was narrowed the same
day this was written to fighters carrying NOTHING --- Ike Clanton, unarmed
against revolvers. This is the case that narrowing gave up: armed, and it
makes no difference.

At the O.K. Corral seven men shot Power Lad for twenty-eight Phases. The
shots landed. His 25 rPD ate every one. Nobody stopped, because no
doctrine in the catalogue reads a fight and concludes anything.

GATED ON EVIDENCE THE SIDE HAS. Landed blows that did no BODY, counted
per target from the session's log. A miss is not evidence --- you might
hit next time --- and one bounce is bad luck, so the threshold is three.

POOLED ACROSS THE SIDE, because the Earps are a team and so are the
Cowboys. That was a correction from a measurement: at the Corral nineteen
shots were fired at Power Lad, five landed, and no individual ever
reached three, because OCV 5 against DCV 6 misses most of the time. The
proof was on the ground the whole fight and no single man held enough of
it. Three men who each landed one and watched it do nothing have the same
fact between them, and they were close enough to see.

AND ONLY WHEN NOTHING ELSE IS WORKING EITHER. A man landing telling blows
on somebody else is in a fight he may be winning, and leaving it because
one opponent is armoured would be worse advice than none.
"""
from __future__ import annotations

from kirby_combat.futility import anything_working, futile_hits
from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register

#: How many landed, useless blows before a man is entitled to conclude it.
#: A JUDGEMENT. One is luck and two is a coincidence; three is a pattern,
#: and it is the smallest number that is not either of the first two.
PROOF_THRESHOLD = 3


@register
class BreakOffWhenNothingWorks(Tactic):
    name = "break_off_when_nothing_works"
    basis = Basis(
        judgement="a fighter who has landed three blows for nothing has "
                  "learned something, and standing there to learn it again "
                  "is not courage",
    )
    #: Above `keep_range` (45) and `sustained_fire` (36), which are the two
    #: that keep a man shooting; below `withdraw_when_outmatched` (54),
    #: because having nothing at all is a stronger reason to go than having
    #: something that does not work.
    priority = 50
    narrative_summary = (
        "You have hit that one squarely, more than once, and it has done "
        "nothing at all -- what you are carrying cannot hurt it. Standing "
        "here spends Phases proving the same thing again. Break off and "
        "get clear."
    )

    @staticmethod
    def _side(situation: Situation) -> tuple[str, ...]:
        """The allies whose failures this actor watched.

        A side pools what it saw; the room does not. An enemy's bullet
        bouncing teaches you nothing you can act on -- he is a man you are
        trying to kill, and you are not comparing notes.
        """
        return tuple(getattr(a, "id", "") for a in (situation.allies or []))

    def applicable(self, situation: Situation) -> bool:
        if situation.session is None or not situation.enemies:
            return False
        actor_id = getattr(situation.actor, "id", "")
        if anything_working(situation.session, actor_id):
            return False
        futile = futile_hits(situation.session, actor_id,
                             also=self._side(situation))
        living = {getattr(e, "id", "") for e in situation.enemies}
        return any(count >= PROOF_THRESHOLD
                   for target, count in futile.items() if target in living)

    def execute(self, situation: Situation) -> Plan:
        actor_id = getattr(situation.actor, "id", "")
        futile = futile_hits(situation.session, actor_id,
                             also=self._side(situation))
        worst = max(futile, key=lambda t: futile[t]) if futile else None
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Landed {futile.get(worst, 0)} blows on {worst} for no BODY "
                f"at all, and nothing else this fighter has tried has hurt "
                f"anybody. What he is carrying does not work here."
            ),
            steps=[
                PlanStep(
                    kind="disengage",
                    notes=(
                        "Break off. Not a rout -- a man who has proved his "
                        "weapon useless is spending Phases to prove it again."
                    ),
                ),
            ],
            expected_outcome=(
                "Leaves the field rather than continuing to attack something "
                "his weapon demonstrably cannot hurt."
            ),
        )
