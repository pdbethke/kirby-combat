"""Hardened, Impenetrable and Penetrating do something.

All three are read off the character sheet and were read by NOTHING.
`hero_view` parses them --- `_modifier_levels(power, "HARDENED")` at
line 1589, `"IMPENETRABLE"` at 1590, `"PENETRATING"` at 1932 --- and sets
them on `DefenseItem.hardened` / `.impenetrable` / `AttackPower.penetrating`.
No resolver ever looked at any of them. Armor Piercing was wired
(`defense.py` halves both totals), so AP worked and nothing in the game
could resist it, and a Penetrating attack resolved exactly like an
ordinary one.

Found by sweeping every dataclass field in the engine for reads. The same
shape as the fourteen before it: computed, correct, delivered nowhere ---
except that these three are bought with points on a character sheet, so a
player paid for them.

THE RULES, quoted from the book rather than derived.

6E1 p.149. "Hardened (+1/4): A Defense Power with this Advantage is
particularly resistant to Armor Piercing attacks. An attack with Armor
Piercing applies normally against a Hardened defense; the usual 'halving'
effect is ignored. Characters can buy Hardened multiple times to
counteract multiple purchases of Armor Piercing." And, decisively for how
this is implemented: "A character cannot have partially Hardened
defenses. A given defense must be all Hardened, or it's not Hardened at
all. A character can, however, have some defenses that are Hardened, and
others that are not." So AP halves the UNHARDENED portion and leaves the
rest alone --- not the whole total, which is what a single flag on the
target would have given.

6E1 p.149. "Impenetrable (+1/4): ... An attack with Penetrating applies
normally ...; the usual 'minimum damage' effect is ignored. Characters
can buy Impenetrable multiple times to counteract multiple purchases of
Penetrating."

6E1 p.188 gives Penetrating's minimum in a worked example: "if a
character with 50% Damage Reduction is hit by an RKA 4d6, Penetrating
that does 12 BODY, 36 STUN (roll of 5, 3, 2, 2), and his defenses plus
Damage Reduction would reduce the BODY damage to 2 BODY, he takes 4 BODY
- the minimum BODY damage the Penetrating attack can cause with that
roll." Four dice, four BODY: ONE BODY PER DIE, and it is a floor rather
than an addition.

WHAT IS NOT CLAIMED. A combatant's own PD/ED can be Hardened in the book
and this model has nowhere to record that --- `DefenseItem` carries the
flag, `HeroCombatStats` does not. Natural defenses are therefore treated
as unhardened, which is the pre-existing behaviour and is stated here
rather than hidden.
"""
from __future__ import annotations

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.models import AttackPower, DefenseItem
from kirby_combat.resolution.defense import compute_defense


def _gun(dice=4, *, ap=0, pen=0, killing=True):
    return AttackPower(
        xmlid="RKA" if killing else "ENERGYBLAST", name="gun",
        damage_dice=dice, half_die=False, plus_one=False,
        damage_type="killing" if killing else "normal",
        defense_type="pd", range_m=50.0, uses_str=False, str_min=0,
        armor_piercing=ap, penetrating=pen, increased_stun_mult=0,
        is_ranged=True, source_id="gun")


def _armour(pd, *, hardened=0, impenetrable=0, name="plate"):
    """Resistant Protection: rPD counts toward total PD as well, so both
    are set -- an item with rpd and no pd reports a resistant total larger
    than the total it is part of."""
    return DefenseItem(name=name, pd=pd, rpd=pd, is_resistant=True,
                       hardened=hardened, impenetrable=impenetrable)


def _target(defenses):
    return synthetic_combatant(
        id="c1", name="Target", ocv=5, dcv=5, omcv=3, dmcv=3, spd=4, dex=13,
        ego=10, str_=20, con=15, pre=10, rec=5,
        pd=0, ed=0, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=30, max_body=10, max_end=30,
        current_stun=30, current_body=10, current_end=30,
        knockback_resistance=0, defenses=defenses,
    )


# ---- Hardened vs Armor Piercing (6E1 p.149) ----

def test_armor_piercing_halves_an_ordinary_defense():
    """The behaviour that already worked, pinned so the fix cannot break
    it."""
    target = _target([_armour(8)])
    out = compute_defense(target, _gun(ap=1))
    assert out.resistant_defense == 4


def test_hardened_ignores_the_halving():
    target = _target([_armour(8, hardened=1)])
    out = compute_defense(target, _gun(ap=1))
    assert out.resistant_defense == 8


def test_one_level_of_hardened_does_not_stop_two_of_armor_piercing():
    """"Characters can buy Hardened multiple times to counteract multiple
    purchases of Armor Piercing" -- so it is level against level."""
    target = _target([_armour(8, hardened=1)])
    out = compute_defense(target, _gun(ap=2))
    assert out.resistant_defense == 4


def test_some_defenses_hardened_and_others_not():
    """The sentence that decides the implementation: AP halves the
    unhardened portion and leaves the hardened alone. A single flag on the
    target could not express this."""
    target = _target([_armour(8, hardened=1, name="plate"),
                     _armour(4, name="vest")])
    out = compute_defense(target, _gun(ap=1))
    assert out.resistant_defense == 8 + 2


# ---- Penetrating, and Impenetrable against it (6E1 p.149, p.188) ----

def test_penetrating_floors_the_body_at_one_per_die():
    """THE BOOK'S OWN EXAMPLE, 6E1 p.188. "if a character ... is hit by an
    RKA 4d6, Penetrating that does 12 BODY, 36 STUN (roll of 5, 3, 2, 2),
    and his defenses ... would reduce the BODY damage to 2 BODY, he takes
    4 BODY - the minimum BODY damage the Penetrating attack can cause with
    that roll." Four dice, four BODY.

    Here the defence is heavy enough to stop the lot, which is the case
    the floor exists for."""
    from kirby_combat.resolution.penetrating import penetrating_floor

    assert penetrating_floor(_gun(dice=4, pen=1), _target([_armour(30)])) == 4


def test_it_is_a_floor_and_not_a_bonus():
    """A Penetrating attack that already gets more than its minimum
    through does not get the minimum added on top."""
    from kirby_combat.resolution.penetrating import penetrating_floor

    floor = penetrating_floor(_gun(dice=4, pen=1), _target([_armour(0)]))
    assert floor == 4, "the floor is the same number; the caller takes max()"


def test_no_penetrating_no_floor():
    from kirby_combat.resolution.penetrating import penetrating_floor

    assert penetrating_floor(_gun(dice=4), _target([_armour(30)])) == 0


def test_impenetrable_ignores_the_minimum():
    """6E1 p.149: "An attack with Penetrating applies normally ...; the
    usual 'minimum damage' effect is ignored." """
    from kirby_combat.resolution.penetrating import penetrating_floor

    target = _target([_armour(30, impenetrable=1)])
    assert penetrating_floor(_gun(dice=4, pen=1), target) == 0


def test_one_impenetrable_does_not_stop_two_penetrating():
    """"Characters can buy Impenetrable multiple times to counteract
    multiple purchases of Penetrating" -- level against level, the same
    way Hardened meets Armor Piercing."""
    from kirby_combat.resolution.penetrating import penetrating_floor

    target = _target([_armour(30, impenetrable=1)])
    assert penetrating_floor(_gun(dice=4, pen=2), target) == 4


def test_a_half_die_counts():
    """`damage_dice` is whole dice and `half_die` is the rest of the
    attack; a 2d6+1/2 Penetrating attack rolls three dice."""
    from kirby_combat.resolution.penetrating import penetrating_floor

    gun = _gun(dice=2, pen=1)
    gun.half_die = True
    assert penetrating_floor(gun, _target([_armour(30)])) == 3


def test_the_resolver_actually_applies_it():
    """The wiring, not the arithmetic. Without this the module is another
    correct calculation delivered nowhere."""
    from kirby_combat.actions import resolve_attack
    from kirby_combat.models import AttackInput, DiceValues
    from kirby_combat.template import CombatTemplate

    # THE BOOK'S ROLL, so nothing here depends on a seed: 6E1 p.188's
    # example is an RKA 4d6 Penetrating rolling 5, 3, 2, 2 for 12 BODY.
    # Against 30 resistant DEF the defences stop all of it, and the
    # minimum is what gets through.
    dice = DiceValues(to_hit=[1, 1, 1], damage=[5, 3, 2, 2],
                      stun_multiplier=[3])
    target = _target([_armour(30)])
    out = resolve_attack(
        AttackInput(attacker=_target([]), target=target,
                    power=_gun(dice=4, pen=1), distance_m=5.0, aim=None,
                    dice=dice),
        CombatTemplate.default_6e_superheroic(),
    )
    assert out.body_dealt == 4, (
        "a Penetrating attack must get its minimum BODY through 30 DEF; "
        f"audit: {out.audit_trail}"
    )


def test_impenetrable_armour_stops_it_in_the_resolver_too():
    from kirby_combat.actions import resolve_attack
    from kirby_combat.models import AttackInput, DiceValues
    from kirby_combat.template import CombatTemplate

    dice = DiceValues(to_hit=[1, 1, 1], damage=[5, 3, 2, 2],
                      stun_multiplier=[3])
    target = _target([_armour(30, impenetrable=1)])
    out = resolve_attack(
        AttackInput(attacker=_target([]), target=target,
                    power=_gun(dice=4, pen=1), distance_m=5.0, aim=None,
                    dice=dice),
        CombatTemplate.default_6e_superheroic(),
    )
    assert out.body_dealt == 0
