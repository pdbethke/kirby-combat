"""Surprised — what it costs to be hit by something you never saw.

6E2 p.52 splits the rule in two by whether the target was IN combat:

  * Out of combat: 1/2 DCV, **2x STUN**, and Placed Shot penalties halved.
    "Double the STUN damage before applying defenses (and, in campaigns
    using the Hit Locations rules, before applying the STUN modifier for
    a location)."
  * In combat: 1/2 DCV only. Regular STUN, normal Placed Shot penalties.

THE ORDERING IS THE RULE. Doubling after defenses would turn a hit that
should leave a man reeling into one that leaves him untouched: 10 STUN
against 12 defense is (10-12)*2 = 0 done backwards, and (10*2)-12 = 8
done the way the book says. It is the same asymmetry the killing STUN
multiplier has -- see `resolution/hit_location.py`, which multiplies
killing STUN before defenses and normal STUN after -- and it is why this
is a function the damage step calls rather than a factor a caller applies
wherever it likes.

WHAT WAS ALREADY HERE. `perception.is_surprised` has answered the
perception half since the perception line shipped, and its own docstring
says the rest "is applied by the driver, which knows the combat clock".
The driver never applied it. Before this module, nothing outside
`perception.py` mentioned surprise at all, so no resolver had ever
halved a DCV or doubled a STUN for it.

WHY THIS IS NOT FLANKING. p.52 goes out of its way to refuse the
positional reading: "if the character knows about or can see an opponent,
that opponent can't get a Surprised bonus just by making a Half Move
behind the character before attacking ... moving behind a character
before attacking does not per se earn an attacker a Surprised bonus."
Surprise is a question about PERCEPTION and expectation, never about
geometry, which is why `surprise_for` takes "does the target perceive the
attacker" and no angle at all.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from dataclasses import dataclass

#: 6E2 p.52. Both halvings, and the doubling.
SURPRISED_DCV_FACTOR = 0.5
OUT_OF_COMBAT_STUN_MULTIPLIER = 2
OUT_OF_COMBAT_PLACED_SHOT_FACTOR = 0.5

#: The Skill that opts out of the whole rule. It is a SKILL in the build
#: engine (`kirby_cost.objects.skills.defense_maneuver`), not a Talent, so
#: the Danger Sense scan in `perception` would not have found it.
DEFENSE_MANEUVER = "DEFENSE_MANEUVER"


@dataclass(frozen=True)
class Surprise:
    """What being Surprised does to one attack.

    An object rather than three loose numbers because the three move
    together and are wrong apart: `stun_multiplier` and
    `placed_shot_factor` both depend on `out_of_combat` while
    `dcv_factor` does not, and a caller that reads them individually will
    eventually read one of them from the wrong branch.

    ``if surprise:`` asks the only question most callers have.
    """

    applies: bool
    out_of_combat: bool = False

    def __bool__(self) -> bool:
        return self.applies

    @property
    def dcv_factor(self) -> float:
        """1/2 DCV, in or out of combat alike (6E2 p.52)."""
        return SURPRISED_DCV_FACTOR if self.applies else 1.0

    @property
    def stun_multiplier(self) -> int:
        """2x STUN, and ONLY out of combat.

        In combat the target "takes regular STUN damage from attacks" --
        p.52 is explicit, because anyone already in a fight expects to be
        attacked and has merely been caught from an unexpected quarter.
        """
        return (OUT_OF_COMBAT_STUN_MULTIPLIER
                if self.applies and self.out_of_combat else 1)

    @property
    def placed_shot_factor(self) -> float:
        """Placed Shot penalties halved, and again only out of combat."""
        return (OUT_OF_COMBAT_PLACED_SHOT_FACTOR
                if self.applies and self.out_of_combat else 1.0)

    def __str__(self) -> str:
        if not self.applies:
            return "not surprised"
        where = "out of combat" if self.out_of_combat else "in combat"
        return f"Surprised ({where}, 6E2 p52)"


def has_defense_maneuver(target) -> bool:
    """6E2 p.52: "he's automatically prepared for them".

    Scans skills, talents and powers rather than one of the three. It is
    a Skill on a real build; the breadth is there because synthetic
    fixtures and alternate load shapes put abilities wherever they like,
    exactly as `perception._has_talent` already reasons about Danger
    Sense.
    """
    hero = getattr(target, "hero", None) or target
    for collection in ("skills", "talents", "powers"):
        for item in getattr(hero, collection, None) or []:
            if (getattr(item, "xmlid", None) or "").upper() == DEFENSE_MANEUVER:
                return True
    return False


def _is_unconscious(target) -> bool:
    """Knocked Out or dying. p.52 names the unconscious explicitly."""
    state = getattr(target, "state", None)
    if state is None:
        return False
    return (getattr(state, "current_stun", 1) or 0) <= 0


def surprise_for(
    *,
    target,
    perceives_attacker: bool,
    out_of_combat: bool | None = None,
) -> Surprise:
    """Decide what this attack's surprise is worth.

    ``perceives_attacker`` is the perception question, which
    `perception.is_surprised` already answers against senses, Invisibility,
    Stealth and Danger Sense. It is passed IN rather than computed here so
    this module stays a pure reading of p.52 and there is exactly one
    perception model in the engine.

    ``out_of_combat`` defaults to the honest answer for a fight: everyone
    in a CombatSession expects to be attacked, which p.52 says in as many
    words, so the doubled STUN is the exception rather than the state a
    driver falls into by accident. The unconscious are the exception the
    book itself names. A GM -- or an adjudicating model -- can say
    otherwise by passing it.
    """
    if has_defense_maneuver(target):
        return Surprise(applies=False)
    if perceives_attacker:
        return Surprise(applies=False)
    if out_of_combat is None:
        out_of_combat = _is_unconscious(target)
    return Surprise(applies=True, out_of_combat=bool(out_of_combat))


def doubled_stun(stun: int, surprise: Surprise) -> int:
    """Apply p.52's doubling, BEFORE defenses and before any location.

    A function rather than a caller multiplying by `stun_multiplier`
    itself, so that the one place the ordering matters is named and can be
    pointed at from the damage step.
    """
    return int(stun) * surprise.stun_multiplier
