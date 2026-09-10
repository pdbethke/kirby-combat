"""A bullet does BODY times something. The something was always 1.

6E2 p.100: "To determine the STUN done, the character rolls a STUN
Multiplier -- 1/2d6 -- and multiplies the result by the amount of BODY
done." The book's own example rolls a 3 and does 7 x 3 = 21 STUN.

`compute_damage` implements that faithfully. It reads the roll from
`DiceValues.stun_multiplier`, and NOT ONE construction site in the engine
has ever written that field:

    stun_mult_die = dice.stun_multiplier[0] if dice.stun_multiplier else 1

The fallback is 1, `(1 + 1) // 2` is 1, and the multiplier comes out at
the template base every single time. Every killing attack this engine has
resolved in a campaign without Hit Locations -- which is the default
superheroic template, and everything the AI line runs on -- did STUN
exactly equal to BODY.

HEROIC CAMPAIGNS WERE FINE, which is why this survived a benchmark built
on one. 6E2 p.100 offers the Hit Location table "instead of a rolled STUN
Multiplier", and `actions/base.py` takes that branch, overriding the roll
with the location's STUNx. So the O.K. Corral's shotgun to the shoulder
correctly did x3. Turn hit locations off and the roll underneath is
exposed, stuck at its minimum.

The same shape as the range penalty, MovementResolved and the END spend:
a field computed for, correct in the reader, and delivered by nobody.
"""
from __future__ import annotations

from collections import Counter

from kirby_combat.models import AttackPower, DiceValues
from kirby_combat.resolution.damage import compute_damage
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

SUPER = CombatTemplate.default_6e_superheroic()


def _rka() -> AttackPower:
    return AttackPower(
        xmlid="RKA", name="rka", damage_dice=2, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=50.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True,
    )


def test_the_half_die_maps_to_one_two_or_three():
    """(n+1)//2 over a d6 gives 1,1,2,2,3,3 -- the reader was always right."""
    seen = {
        compute_damage(
            _rka(), DiceValues(damage=[3, 4], stun_multiplier=[face]), SUPER,
        ).stun_multiplier
        for face in range(1, 7)
    }
    assert seen == {1, 2, 3}


def test_a_fight_rolls_the_multiplier():
    """Through the loop, not through a hand-built DiceValues. A killing
    attack that never varies its multiplier is the bug."""
    import kirby_combat.actions.base as base

    seen: Counter[int] = Counter()
    original = base.compute_damage

    def watch(power, dice, template, *args, **kwargs):
        result = original(power, dice, template, *args, **kwargs)
        if power.damage_type == "killing":
            seen[result.stun_multiplier] += 1
        return result

    base.compute_damage = watch
    try:
        # The shootout is a HEROIC fight, so `actions/base` will override
        # each multiplier with the Hit Location's STUNx afterwards. That
        # does not matter here: what is under test is whether the LOOP
        # hands `compute_damage` a rolled die at all, and that plumbing is
        # the same either way.
        from examples.the_shootout_we_can_publish import the_fight

        for seed in range(1, 16):
            the_fight(seed)
    finally:
        base.compute_damage = original

    assert sum(seen.values()) > 20, f"too few killing attacks to judge: {seen}"
    assert len(seen) > 1, (
        f"every killing attack in eleven fights used the same STUN "
        f"multiplier: {dict(seen)}"
    )
    assert set(seen) <= {1, 2, 3}, dict(seen)
