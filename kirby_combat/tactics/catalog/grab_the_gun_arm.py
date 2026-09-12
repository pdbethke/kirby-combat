"""Grab — seize the gun arm of the man standing next to you.

`grab` is offered 10 times in six corral fights and taken zero times, and
behind it sit `escape_str`, `escape_attack` and `release_held`, none of
which has EVER been offered in any benchmark. The escape family needs
somebody to be holding somebody; nobody ever grabs. **One doctrine gap
gates four action kinds.**

WHY `grab_and_throw` DOES NOT COVER THIS. That tactic wants the actor's
best attack to be melee --- a gunfighter's best is his revolver --- and
STR 30 for "a competitive grab attempt", which is 6d6 and a superhero.
Every man at the corral is STR 10. Both conditions are right for what it
models and wrong for this: it is about out-muscling somebody, and this is
about a man a metre away who is about to shoot you.

That is a STR-vs-STR contest between equals, which is a coin flip and
still worth it, because the alternative is being shot at point-blank
range. So this gates on REACH and on the target being ARMED, and sets no
STR floor at all.

IT NEEDS REACH, which `Situation` did not carry until today. A Grab is
legal only against a man you can touch; a tactic naming somebody across
the lot has its plan discarded by `TacticChooser`, which is exactly how
`disarm_the_armed` came to fire zero times on the day it was written.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register


def _armed(enemy) -> bool:
    """Carrying something with reach --- a gun, not a fist.

    The same test `disarm_the_armed` uses, and for the same reason: a
    Grab that pins a man's fists buys far less than one that pins the
    hand holding a Colt.
    """
    return any((getattr(a, "range_m", 0) or 0) > 0
               for a in getattr(enemy, "attacks", []))


def _grabbable(situation: Situation) -> list:
    return [
        e for e in situation.enemies_in_reach()
        # `Situation.enemies` is documented living-only and the real
        # caller does not filter the downed out -- the skip every other
        # tactic in this catalogue carries.
        if getattr(e, "current_stun", 1) > 0 and _armed(e)
    ]


@register
class GrabTheGunArm(Tactic):
    name = "grab_the_gun_arm"
    basis = Basis(
        mechanism="6E2 p64",
        judgement="a hand on the gun beats a shot at the man holding it",
    )
    #: Just under `disarm_the_armed` (41). Taking the weapon outright
    #: ends his part in the fight; holding his arm only suspends it, and
    #: costs the grabber DCV while he does it. Both sit below staying
    #: alive (`dodge_under_fire` 52) and below saving somebody who is
    #: dying (`stabilize_the_dying` 57).
    priority = 40
    narrative_summary = (
        "He is within arm's length and his gun is out. Grab the arm — a "
        "STR-vs-STR hold that stops him firing at point-blank range "
        "without killing him. It costs you DCV while you hold on, and he "
        "will try to break free, so it buys time rather than settling "
        "anything. Worth it when the alternative is being shot from a "
        "metre away."
    )

    def applicable(self, situation: Situation) -> bool:
        return bool(_grabbable(situation))

    def execute(self, situation: Situation) -> Plan:
        candidates = _grabbable(situation)
        # The heaviest weapon in reach: the arm worth holding is the one
        # that does the most damage if it is left free.
        target = max(candidates, key=lambda e: max(
            (getattr(a, "damage_dice", 0) or 0) for a in e.attacks
            if (getattr(a, "range_m", 0) or 0) > 0))
        name = getattr(target, "name", None) or getattr(target, "id", "him")
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"{name} is within arm's length with his gun out. A Grab "
                f"stops him firing without killing him (6E2 p64); it costs "
                f"DCV while it holds, and he may break free."
            ),
            steps=[PlanStep(kind="grab", target_id=getattr(target, "id", None))],
        )
