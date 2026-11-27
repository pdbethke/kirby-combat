"""Rearm: an empty gun is dropped or reloaded, and the next one drawn.

THE DEFECT. A fighter whose Charged weapon ran dry had no attack on the menu
and no doctrine about it: Doc Holliday fired his shotgun's two shots at the
O.K. Corral and spent the rest of the fight hiding and dodging with a Colt
in its holster (2026-11-27). `reload` and `holster` made the actions exist;
this is the doctrine that takes them.

THE RULES behind each step: changing Clips is a Full Phase (6E1 p.371), a
Half Phase on a made Fast Draw roll (6E1 p.76); drawing a weapon is a Half
Phase, a Zero Phase with Fast Draw (6E1 p.76); dropping one is a Zero Phase
Action (Peter's ruling, 2026-11-27).

JUDGEMENT: with nothing to shoot, rearming beats every other use of the
Phase; reload before swapping guns (the gun he chose to carry first), and a
gun he cannot reload is let fall rather than holstered when he needs the
hand now.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register

_REARM = ("reload", "fast_reload", "drop_weapon", "fast_draw_weapon", "draw_weapon")


def _has_another_gun(situation: Situation) -> bool:
    from kirby_combat.grips import holstered_weapon_ids

    session = getattr(situation, "session", None)
    return session is not None and bool(holstered_weapon_ids(session, situation.actor.id))


@register
class Rearm(Tactic):
    name = "rearm"
    basis = Basis(mechanism="6E1 p371",
                  judgement="with nothing to shoot, reload or swap guns before anything else")
    #: Above `fight_from_cover` and the withdrawals: a man with an empty gun
    #: in cover is not fighting from it.
    priority = 58
    narrative_summary = (
        "Your weapon is empty and nothing else in your hands can fire. Reload "
        "if you have a spare clip (a Full Phase, 6E1 p.371); otherwise let the "
        "empty gun fall (no time) and draw the next (a Half Phase, 6E1 p.76)."
    )

    def applicable(self, situation: Situation) -> bool:
        if getattr(situation, "out_of_turn", None) is not None:
            return False
        kinds = set(situation.menu_kinds)
        if situation.has_ranged_offer:
            return False                    # something still fires; a punch is not a gun
        return bool(self._steps(situation, kinds))

    def _steps(self, situation: Situation, kinds: set) -> list[str]:
        out = [k for k in ("reload", "fast_reload", "fast_draw_weapon", "draw_weapon") if k in kinds]
        # Let the empty gun fall only to free a hand for another (ruling-free
        # judgement: dropping with nothing to draw is a gun thrown away).
        if "drop_weapon" in kinds and _has_another_gun(situation) and not out:
            out.append("drop_weapon")
        return out

    def execute(self, situation: Situation) -> Plan:
        order = self._steps(situation, set(situation.menu_kinds))
        return Plan(tactic_name=self.name,
                    rationale="nothing in your hands can fire: " + ", then ".join(order),
                    steps=[PlanStep(kind=k) for k in order])
