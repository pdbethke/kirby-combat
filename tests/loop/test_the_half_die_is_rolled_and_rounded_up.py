"""A half die is a die, and it rounds up — 6E2 p.100.

"If a character has to roll a half die (½d6) ... Roll the half die
separately ... The face value of the die is multiplied by one-half and
rounded up to get the number of STUN done. The ½d6 does 1 BODY if the roll
is a 4, 5, or 6."

TWO DEFECTS, both found by the maneuvers work:

1. `compute_damage` halved the face ROUNDING DOWN (`value // 2`), so a 1 did
   no STUN and a 5 did 2; and it gave BODY only on a 5 or 6.
2. `_resolve_attack` rolled `damage_dice` dice -- the WHOLE dice -- and
   `compute_damage` reads the last die it is handed as the ½d6. So a 2½d6
   attack rolled two dice and did 1½d6. Every half-die attack in the engine
   lost a whole die.

Through `resolve_chosen`, so it is the live path that is pinned. FakeRoller
refuses a roll of the wrong size, which is what makes defect 2 fail loudly
on origin/main instead of quietly using the wrong dice.
"""
from __future__ import annotations

from dataclasses import replace

from conftest import blast, fighter, session_of      # tests/loop/conftest.py
from kirby_dice import FakeRoller

from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _half_die_blast():
    """A 2½d6 Blast."""
    return replace(blast("brute-eb", dice=2), half_die=True)


def _shoot(damage: list[int]):
    session = session_of(
        fighter("brute", side=Side.named("villains"), dice=2),
        fighter("mark", side=Side.named("heroes"), dice=2),
    )
    power = _half_die_blast()
    action = LegalAction(
        action_id="attack:mark", kind="attack", target_id="mark",
        power_xmlid=power.xmlid, power_name=power.name, summary="attack",
        _attack_view=power,
    )
    # to-hit 3 (always hits), damage, hit location, STUN multiplier.
    roller = FakeRoller([[1, 1, 1], damage, [3, 3, 3], [1]])
    resolved = resolve_chosen(
        session, session.combatants["brute"], action,
        template=TEMPLATE, roller=roller,
    )
    return resolved.result


def test_a_two_and_a_half_die_attack_rolls_three_dice():
    """Defect 2. On origin/main this asks FakeRoller for 2 dice and the
    fixture's 3 are refused."""
    result = _shoot([4, 3, 5])
    # 4 + 3 whole dice, and the ½d6 face 5 rounds UP to 3.
    assert result.damage.stun == 10
    # 1 + 1 for the whole dice, 1 for a half die of 4+.
    assert result.damage.body == 3


def test_a_half_die_of_one_still_does_a_point():
    """Rounded up, a 1 is one STUN -- it was zero."""
    result = _shoot([2, 2, 1])
    assert result.damage.stun == 5
    assert result.damage.body == 2


def test_a_half_die_of_four_does_a_body():
    """"1 BODY if the roll is a 4, 5, or 6" -- the 4 did none."""
    result = _shoot([1, 1, 4])
    assert result.damage.stun == 4
    assert result.damage.body == 1


def test_the_half_die_table():
    from kirby_combat.resolution.damage import half_die_body, half_die_face

    assert [half_die_face(v) for v in range(1, 7)] == [1, 1, 2, 2, 3, 3]
    assert [half_die_body(v) for v in range(1, 7)] == [0, 0, 0, 1, 1, 1]
