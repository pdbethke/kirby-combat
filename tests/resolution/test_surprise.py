"""Surprised — 6E2 p.52, the rule the engine could answer and never asked.

    "A character Surprised while out of combat is at 1/2 DCV and takes 2x
    STUN from the attack; moreover, the penalty for any Placed Shot is
    halved. Double the STUN damage BEFORE applying defenses (and, in
    campaigns using the Hit Locations rules, before applying the STUN
    modifier for a location) ... A character Surprised while in combat is
    at 1/2 DCV, but Placed Shot penalties are not halved, and he takes
    regular STUN damage from attacks."

`perception.is_surprised` has answered the perception half since the
perception line shipped, and its own docstring says the rest "is applied
by the driver, which knows the combat clock". The driver never applied
it: NOTHING outside `perception.py` mentions surprise at all, so neither
the halved DCV nor the doubled STUN has ever reached a resolver.

Two other clauses of p.52 that are easy to lose:

  * Defense Maneuver. "if the character has Defense Maneuver, whether
    he's expecting surprise attacks really doesn't matter; he's
    automatically prepared for them." It is a SKILL in the build engine
    (`DEFENSE_MANEUVER`), not a Talent, so the Danger Sense scan next
    door would not have found it.
  * The unconscious. "an unconscious (Knocked Out) or asleep character
    takes 2x STUN" — out of combat by definition, however busy the fight
    around him.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

import pytest

from kirby_combat.resolution.surprise import Surprise, surprise_for


class _Stub:
    """The smallest thing that answers the questions Surprise asks."""

    def __init__(self, *, skills=(), talents=(), stun=20):
        self.hero = self
        self.skills = [type("S", (), {"xmlid": x})() for x in skills]
        self.talents = [type("T", (), {"xmlid": x})() for x in talents]
        self.powers = []
        self.state = type("St", (), {"current_stun": stun, "current_body": 5})()


# ---- the object, in isolation from perception ----------------------------

def test_in_combat_halves_dcv_and_leaves_stun_alone():
    s = Surprise(applies=True, out_of_combat=False)
    assert s.dcv_factor == 0.5
    assert s.stun_multiplier == 1
    assert s.placed_shot_factor == 1.0
    assert bool(s) is True


def test_out_of_combat_also_doubles_stun_and_halves_placed_shots():
    s = Surprise(applies=True, out_of_combat=True)
    assert s.dcv_factor == 0.5
    assert s.stun_multiplier == 2
    assert s.placed_shot_factor == 0.5


def test_not_surprised_changes_nothing():
    s = Surprise(applies=False, out_of_combat=True)
    assert (s.dcv_factor, s.stun_multiplier, s.placed_shot_factor) == (1.0, 1, 1.0)
    assert bool(s) is False


# ---- the decision --------------------------------------------------------

def test_defense_maneuver_is_never_surprised():
    """p.52: "he's automatically prepared for them"."""
    target = _Stub(skills=["DEFENSE_MANEUVER"])
    assert surprise_for(target=target, perceives_attacker=False).applies is False


def test_a_target_who_cannot_perceive_the_attacker_is_surprised():
    assert surprise_for(target=_Stub(), perceives_attacker=False).applies is True


def test_a_target_who_sees_it_coming_is_not():
    assert surprise_for(target=_Stub(), perceives_attacker=True).applies is False


def test_an_unconscious_character_is_out_of_combat():
    """p.52 names them explicitly, and a fight raging around a man who
    cannot see it does not make him a participant."""
    out = surprise_for(target=_Stub(stun=-3), perceives_attacker=False)
    assert out.applies is True
    assert out.out_of_combat is True
    assert out.stun_multiplier == 2


def test_a_conscious_fighter_is_in_combat_by_default():
    """Everyone in a CombatSession expects to be attacked -- p.52 says so
    in as many words -- so the doubled STUN is the exception, not the
    default a driver falls into."""
    out = surprise_for(target=_Stub(), perceives_attacker=False)
    assert out.out_of_combat is False
    assert out.stun_multiplier == 1


def test_the_gm_can_say_out_of_combat():
    """p.52 leaves 'expecting any attacks' to common sense, so the
    caller must be able to overrule the default without editing it."""
    out = surprise_for(target=_Stub(), perceives_attacker=False,
                       out_of_combat=True)
    assert out.stun_multiplier == 2


@pytest.mark.parametrize("stun_before_defenses, defense, expected", [
    (10, 4, 16),     # doubled to 20 FIRST, then 4 stopped -> 16
    (10, 12, 8),     # doubled to 20, then 12 stopped -> 8
])
def test_doubling_happens_before_defenses(stun_before_defenses, defense, expected):
    """The ordering is the whole rule. Doubling AFTER defenses would give
    (10-4)*2 = 12 and (10-12)*2 = 0 -- both wrong, and the second turns a
    survivable hit into nothing at all."""
    from kirby_combat.resolution.surprise import doubled_stun

    got = max(0, doubled_stun(stun_before_defenses,
                              Surprise(applies=True, out_of_combat=True)) - defense)
    assert got == expected
