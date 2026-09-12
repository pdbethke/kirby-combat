"""Disarm — take the gun, which is the whole reason the Earps were there.

The catalogue held 26 tactics and not one of them took a man's weapon,
while the corral's Earps carry this in the scene file as their stated
`Side.objective`:

    "Disarm the Cowboys and place them under arrest.
     Shoot the men, not the buildings."

and the Cowboys answer it: "Do not be disarmed." The Brief renders that
objective to whoever is deciding, `disarm` is enumerated and resolvable,
and a model that reads the page chose it. The rule-based chooser could
not, ever --- so doctrine was structurally incapable of pursuing its own
side's goal.

THIS DOES NOT READ THE OBJECTIVE. Gating on that prose would mean
parsing it, and a regex over a GM's sentence is not a rule. Taking an
armed man's weapon is sound doctrine wherever it is legal, so the tactic
says so plainly and lets legality decide --- the catalogue's own
contract: "WHEN DOCTRINE AND LEGALITY DISAGREE, LEGALITY WINS." A Disarm
against a man out of reach never reaches the menu and the plan is
skipped.

PRIORITY 41, deliberately modest. A Disarm is a Half Phase attack that
does no damage and can fail; it is worth a Phase when the man is in
reach and his gun is the threat, and it must not outrank keeping
yourself alive (`take_cover_when_hurt` 55, `dodge_under_fire` 52) or
saving somebody who is dying (`stabilize_the_dying` 57). In six fights it
is legal about four times, so this changes little and unlocks the thing
the side actually wants.
"""
from __future__ import annotations

from kirby_combat.tactics.base import Basis, Plan, PlanStep, Situation, Tactic
from kirby_combat.tactics.library import register


def _is_a_weapon(attack) -> bool:
    """A thing that can be taken out of a hand.

    Reach is the test, not the xmlid: a Disarm removes a WEAPON, and a
    man's fists are not one. `range_m > 0` is how this package already
    separates a gun from a punch (`_is_melee`), so the same question gets
    the same answer here.
    """
    return (getattr(attack, "range_m", 0) or 0) > 0


def _armed_enemies(situation: Situation) -> list:
    out = []
    for e in situation.enemies:
        # `Situation.enemies` is documented living-only and the real
        # caller does NOT filter the downed out -- the same skip
        # `dodge_under_fire` carries, and for the same reason.
        if getattr(e, "current_stun", 1) <= 0:
            continue
        if any(_is_a_weapon(a) for a in getattr(e, "attacks", [])):
            out.append(e)
    return out


@register
class DisarmTheArmed(Tactic):
    name = "disarm_the_armed"
    basis = Basis(
        mechanism="6E2 p66",
        judgement="a man without his gun is out of the fight without being killed",
    )
    priority = 41
    narrative_summary = (
        "He is close enough to reach and his weapon is the threat — take "
        "it. A Disarm is a STR contest that ends his contribution without "
        "killing him, which matters when your side wants prisoners rather "
        "than bodies. It does no damage, so it is worth a Phase only "
        "while he is still armed and still standing."
    )

    def applicable(self, situation: Situation) -> bool:
        return bool(_armed_enemies(situation))

    def execute(self, situation: Situation) -> Plan:
        armed = _armed_enemies(situation)
        # The biggest gun, for the RATIONALE only.
        loudest = max(armed, key=lambda e: max(
            (getattr(a, "damage_dice", 0) or 0)
            for a in e.attacks if _is_a_weapon(a)))
        name = getattr(loudest, "name", None) or getattr(loudest, "id", "him")

        # NO TARGET NAMED, and that is a concession rather than a
        # preference. A Disarm is only legal against a man already in
        # reach, and THE TACTIC LAYER CANNOT SEE REACH --- `Situation`
        # carries actor, allies, enemies, complications and skills, and
        # no distance of any kind. Naming the biggest gun on the field
        # therefore named a man who was usually across the lot, and
        # `TacticChooser` discards a plan whose target is not on the menu
        # ("Firing the right KIND at the wrong MAN is worse than falling
        # through"). Measured: with a name, this tactic fired zero times.
        #
        # Target-less, the chooser takes `offers[0]` --- the first Disarm
        # the enumerator produced, which is by construction against an
        # adjacent armed man. That is the right answer here even though
        # the catalogue rightly warns that "DOCTRINE NAMES A VICTIM, AND
        # IT IS NOT DECORATION": for this maneuver, legality already
        # narrows the field to men worth naming.
        #
        # The real fix is reach on `Situation`, which is a change to the
        # tactic layer's contract and is recorded in docs/gaps.md rather
        # than smuggled in here.
        return Plan(
            tactic_name=self.name,
            rationale=(
                f"An armed man is in reach --- {name} carries the heaviest "
                f"weapon on the field. Taking a gun ends its owner's part "
                f"in this without killing him (6E2 p66)."
            ),
            steps=[PlanStep(kind="disarm", target_id=None)],
        )
