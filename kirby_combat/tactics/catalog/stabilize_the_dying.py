"""Stabilize the dying — stop an ally bleeding out before he dies.

Every piece of this was built and wired before the tactic existed: the
bleeding rules, the Dying status, the Paramedics roll and its -1 per -2
BODY, and a `stabilize` offer keyed to the ALLY's condition rather than
the actor's skill. And doctrine never once chose it.

Measured on the corral, six fights: **31 `stabilize` offers, 29 bleeding
ticks, zero attempts to help.** Doc Holliday stood there with PARAMEDICS
11 while men bled. That is a rung worse than this repo's usual "computed,
delivered nowhere" --- it was computed, delivered, offered, and never
chosen, which no unit test can catch.

THE STAKES ARE IN THE RULE. 6E2 p.105/109: a character at 0 or negative
BODY is DYING, loses 1 BODY per Turn, and dies at negative his starting
BODY. Death is inevitable without intervention. 6E2 p.115 gives the
attempt to anybody, "even just the Everyman 8- roll", so this tactic does
NOT gate on having Paramedics --- a bad roll beats no attempt.

KO IS NOT DYING, and the difference decides whether this fires at all. A
man at STUN 0 with BODY intact is unconscious and in no danger; spending
a Full Phase on Paramedics over him wastes it while somebody else bleeds.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register

#: 6E2 p.105 --- 0 BODY is already Dying, not merely hurt.
_DYING_AT_OR_BELOW = 0


def _dead(man) -> bool:
    """At negative his starting BODY he is dead (6E2 p.109), past saving."""
    max_body = getattr(man, "max_body", None)
    return max_body is not None and man.current_body <= -int(max_body)


def _dying_allies(situation: Situation) -> list:
    """Allies at 0 or negative BODY, worst first.

    Worst first because bleeding costs 1 BODY a Turn and death arrives at
    negative starting BODY: the man nearest it is the one who cannot
    wait.
    """
    # BOTH LISTS. A dying man belongs in `fallen_allies`, but reading
    # only that would make this tactic depend on which list a caller
    # happens to put him in -- and the defect this fixes was exactly a
    # caller filling one list and not the other.
    candidates = list(situation.allies or []) + list(
        getattr(situation, "fallen_allies", None) or [])
    dying = [
        a for a in candidates
        if getattr(a, "current_body", 1) is not None
        and getattr(a, "current_body", 1) <= _DYING_AT_OR_BELOW
        and not _dead(a)
    ]
    return sorted(dying, key=lambda a: getattr(a, "current_body", 0))


def _dies_this_turn(man) -> bool:
    """Whether the next bleed (the end of Segment 12) kills him: he loses
    what `bleed_out_body` says and dies at negative his starting BODY
    (6E2 p.109)."""
    from kirby_combat.resolution.bleeding import bleed_out_body

    max_body = getattr(man, "max_body", None)
    if max_body is None:
        return False
    after = man.current_body - bleed_out_body(current_body=man.current_body)
    return after <= -int(max_body)


def _covered_from_every_enemy(situation: Situation) -> bool:
    """Whether he stands behind cover from every enemy still standing.

    Cover is a fact about the target against one shooter (6E2 p.45), so
    covered from one man and in the open to another is in the open. No
    map, or a man the map cannot place, and nobody can say he is covered.
    """
    session = getattr(situation, "session", None)
    scene = getattr(session, "scene", None) if session is not None else None
    if scene is None:
        return False
    from kirby_combat.placement import position_of
    from kirby_world.cover import compute_cover_level

    here = position_of(scene, situation.actor.id)
    if here is None:
        return False
    for enemy in situation.enemies:
        there = position_of(scene, enemy.id)
        if there is None or compute_cover_level(
                shooter_pos=there, target_pos=here,
                target_is_prone_or_diving=False, scene=scene) <= 0:
            return False
    return True


def _to_kneel_for(situation: Situation) -> list:
    """The dying allies worth stopping the fight for, worst first.

    JUDGEMENT (Peter, 2026-11-27), not a rule: 6E2 p.109 says a dying man
    can be stabilized, not when. A man stops fighting to do it only when no
    enemy is standing, or he is in cover from every one, or the man dies
    at the end of this Turn without help. At the corral three Earps
    bandaged Wyatt in the open while the McLaurys shot them down, and
    Wyatt had seven Turns to live.
    """
    dying = _dying_allies(situation)
    if not dying:
        return []
    if not situation.enemies or _covered_from_every_enemy(situation):
        return dying
    return [a for a in dying if _dies_this_turn(a)]


@register
class StabilizeTheDying(Tactic):
    name = "stabilize_the_dying"
    basis = Basis(
        mechanism="6E2 p109",
        judgement=("stop fighting to save him only when it is safe to kneel (no "
                   "enemy standing, or cover from every one) or he dies this Turn "
                   "without help (Peter, 2026-11-27)"),
    )
    #: Above `take_cover_when_hurt` (55) and `withdraw_when_outmatched`
    #: (54) --- those weigh the actor's own skin, and this is somebody
    #: else's life ending on a clock. Below `exploit_susceptibility` (60),
    #: which ends the fight outright and so saves him too.
    priority = 57
    narrative_summary = (
        "An ally is DYING — at or below 0 BODY, losing 1 BODY every Turn, "
        "and he will die without help (6E2 p109). Spend the Phase on "
        "Paramedics to stabilize him. Anyone may try, even on the "
        "Everyman 8- roll, and the attempt is harder the further below 0 "
        "he has bled (-1 per -2 BODY) — so the longer you leave him, the "
        "worse your chances. Shooting can wait; he cannot."
    )

    def applicable(self, situation: Situation) -> bool:
        return bool(_to_kneel_for(situation))

    def execute(self, situation: Situation) -> Plan:
        dying = _to_kneel_for(situation)
        worst = dying[0]
        body = getattr(worst, "current_body", 0)
        name = getattr(worst, "name", None) or getattr(worst, "id", "an ally")
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"{name} is at {body} BODY and bleeding 1 BODY per Turn "
                f"(6E2 p109). Without a Paramedics roll he dies; the roll "
                f"gets harder as he sinks, so it is worth a Phase now."
            ),
            steps=[PlanStep(kind="stabilize", target_id=getattr(worst, "id", None))],
        )
