"""The Coordinate roll is the one on the character sheet.

`coordination.roll_profile` worked the roll out by hand, 9 + DEX/5 for
Teamwork and 9 + INT/5 for Tactics, from whether the xmlid was present at
all. The cost engine already computes every skill's roll
(`HeroCombatant.skill_roll_value`, the door perception, Paramedics and
Acrobatics go through), and the hand-rolled one disagreed with it twice:

- A Familiarity is "an 8- roll" (6E1 p.62), not the full skill. The Cloned
  Soldier's sheet carries Teamwork as a Familiarity, and he coordinated at
  12- (prod, 2026-11-01).
- Levels bought in the skill (+1 for 2 Character Points, 6E1 p.63) never
  reached the roll.
"""
from __future__ import annotations

from kirby_combat.coordination import roll_profile
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant


def _man(**kw):
    return synthetic_combatant(id="m", name="m", side=Side.named("horde"), **kw)


def test_a_teamwork_familiarity_rolls_eight_not_the_full_skill():
    assert roll_profile(_man(dex=20, skills={"TEAMWORK": 8})) == ("Teamwork", 8)


def test_levels_in_teamwork_reach_the_roll():
    # DEX 15 gives 12-, three levels make it 15-; the sheet says 15.
    assert roll_profile(_man(dex=15, skills={"TEAMWORK": 15})) == ("Teamwork", 15)


def test_tactics_is_read_from_the_sheet_too():
    assert roll_profile(_man(int_=10, skills={"TACTICS": 14})) == ("Tactics", 14)


def test_teamwork_still_comes_before_tactics():
    assert roll_profile(
        _man(skills={"TACTICS": 16, "TEAMWORK": 11})) == ("Teamwork", 11)


def test_with_neither_he_still_tries_on_dex_eight():
    assert roll_profile(_man(dex=30, skills={"STEALTH": 14})) == ("DEX", 8)
