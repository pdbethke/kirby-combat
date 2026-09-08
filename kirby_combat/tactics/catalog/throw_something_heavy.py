"""Pick the wagon up and throw it.

PeterB, watching a 400-point brick walk uselessly toward a man with a
rifle: *"he can literally pick up a horse or a wagon and throw it"* /
*"why is that not an option"*.

It was not an option for two reasons and this is the second. The first
was that `pickup` filtered constructs on `kind == "debris"`, a kind
nothing in this engine has ever created --- fixed alongside this, so
anything marked `portable` can now be lifted. The second is that NO
TACTIC EVER ASKED. `pickup` and `throw_object` were reachable only
through the fallback chooser, which takes the first thing on a menu and
has no idea a wagon is a weapon.

WHO THIS IS FOR. A fighter strong enough to lift the furniture whose
enemy is beyond his reach. A brick with claws and an 8m walk, against a
man with a rifle forty metres away, has exactly one good idea and it is
not walking.

Above `close_and_strike` (38), which would otherwise spend the Phase
closing: throwing a tonne of freight is a better use of a Phase than
covering half the ground to somebody who is shooting you. Below
`keep_range` (45), because a fighter who can simply shoot should shoot.

TWO STEPS, IN ORDER, and the order is the whole tactic: throw what you
are holding, or pick something up to throw. The chooser reads a plan's
steps until one is on the menu, so the same tactic covers both Phases of
the act without needing to know which one it is in.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register

#: STR at which a fighter is in the business of throwing furniture. The
#: cost engine's lift curve is 25 * 2^(STR/5) kg, so this is 400kg --- a
#: loaded handcart. A JUDGEMENT: below it, "throw the scenery" is not a
#: plan a person has.
FURNITURE_STR = 20


def _longest_reach(combatant) -> float:
    best = 0.0
    for attack in (getattr(combatant, "attacks", None) or []):
        best = max(best,
                   float(getattr(attack, "range_m", 0.0) or 0.0),
                   float(getattr(attack, "reach_m", 0.0) or 0.0))
    return best


@register
class ThrowSomethingHeavy(Tactic):
    name = "throw_something_heavy"
    basis = Basis(
        judgement="a man strong enough to lift a wagon, facing somebody he "
                  "cannot reach, should throw the wagon",
    )
    priority = 42
    narrative_summary = (
        "You cannot reach him and he is not coming to you. There is "
        "something here heavy enough to matter and you can lift it. "
        "Pick it up and throw it at him."
    )

    def applicable(self, situation: Situation) -> bool:
        enemies = [e for e in (situation.enemies or [])]
        if not enemies:
            return False
        try:
            strength = situation.actor.combat_stats().str_
        except Exception:                                   # noqa: BLE001
            return False
        if strength < FURNITURE_STR:
            return False
        # Only when reaching him is the problem. A brick already in
        # somebody's face should hit him, not go looking for a wagon.
        return _longest_reach(situation.actor) < 2.0

    def execute(self, situation: Situation) -> Plan:
        threat = situation.threat
        target = max(situation.enemies, key=lambda e: threat.get(e.id, 0.0))
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"Cannot reach {getattr(target, 'id', '?')} and is strong "
                f"enough to throw the scenery at him."
            ),
            steps=[
                # Holding something already: throw it.
                PlanStep(kind="throw_object", target_id=getattr(target, "id", None),
                         notes="Hurl what you are holding."),
                # Otherwise get something to throw.
                PlanStep(kind="pickup",
                         notes="Pick up the heaviest thing in reach."),
            ],
            expected_outcome=(
                "A thrown object crossing ground the actor cannot walk, at a "
                "target his fists will never reach."
            ),
        )
