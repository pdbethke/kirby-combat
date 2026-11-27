"""Critical Hits (6E2 p.120), the optional rule a Gritty campaign turns on.

"A 'critical hit' is a blow so accurate it does maximum damage. One occurs
when a character's roll to hit is less than half of what he needed to hit
the target." The page's own examples: needing 12, he must roll 5 or less;
needing 13 (half is 6.5), 6 or less. "Characters may only do critical hits
to living targets."

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from dataclasses import replace

from kirby_combat.actions import resolve_attack
from kirby_combat.models import AttackInput, DiceValues
from kirby_combat.resolution.critical import is_critical


def _attack(blaster, brick, to_hit, power_index=0, damage=None):
    return AttackInput(
        attacker=blaster, target=brick, power=blaster.attacks[power_index],
        distance_m=20, aim=None,
        dice=DiceValues(to_hit=to_hit,
                        damage=damage or [1] * 10, stun_multiplier=[1]),
    )


def test_the_pages_two_examples():
    assert is_critical(roll=5, needed=12) and not is_critical(roll=6, needed=12)
    assert is_critical(roll=6, needed=13) and not is_critical(roll=7, needed=13)


def test_a_critical_does_maximum_damage(blaster, brick, superhero_template):
    """The Energy Blast is 10d6: maximum 60 STUN, 20 BODY (6E2 p.120's own
    example of a Blast). Needed 11 here; a 3 is under half."""
    on = replace(superhero_template, use_critical_hits=True)
    result = resolve_attack(_attack(blaster, brick, [1, 1, 1]), on)
    assert result.critical is True
    assert (result.damage.stun, result.damage.body) == (60, 20)


def test_off_the_rule_does_nothing(blaster, brick, superhero_template):
    off = replace(superhero_template, use_critical_hits=False)
    result = resolve_attack(_attack(blaster, brick, [1, 1, 1]), off)
    assert result.critical is False
    assert result.damage.stun == 10


def test_an_ordinary_hit_is_not_critical(blaster, brick, superhero_template):
    """Needed 11; a 9 hits and is not under half."""
    on = replace(superhero_template, use_critical_hits=True)
    result = resolve_attack(_attack(blaster, brick, [3, 3, 3]), on)
    assert result.hit and result.critical is False


def test_a_miss_is_never_critical(blaster, brick, superhero_template):
    on = replace(superhero_template, use_critical_hits=True)
    result = resolve_attack(_attack(blaster, brick, [6, 6, 6]), on)
    assert not result.hit and result.critical is False


def test_a_killing_critical_maxes_body_and_multiplier(blaster, brick, superhero_template):
    """RKA 3d6+1: maximum BODY 19, and without Hit Locations the maximum
    STUN Multiplier (6E2 p.120: "the maximum possible STUN")."""
    on = replace(superhero_template, use_critical_hits=True)
    result = resolve_attack(_attack(blaster, brick, [1, 1, 1], power_index=1,
                                    damage=[1, 1, 1]), on)
    assert result.critical is True
    assert result.damage.body == 19
    assert result.damage.stun == 19 * result.damage.stun_multiplier
    assert result.damage.stun_multiplier == 3


def test_the_row_says_it_was_critical():
    """On the live path: the door every attack goes through records it."""
    import inspect

    from kirby_combat.actions import recording

    assert '"critical": result.critical' in inspect.getsource(recording)
