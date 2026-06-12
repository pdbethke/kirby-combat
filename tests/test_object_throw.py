"""Thrown-object damage = min(thrower STR dice, object PD+BODY); blunt/sharp (spec §4, 6E2 p82)."""
from kirby_combat.actions.throw import resolve_object_throw


def test_str20_coffee_mug_capped_by_pd_body():
    # STR 20 → 4 STR dice; mug PD1 BODY1 → cap 2 → 2d6 normal
    dice, dtype = resolve_object_throw(thrower_str=20, pd=1, body=1, damage_type="normal")
    assert dice == 2 and dtype == "normal"


def test_str60_boulder_full_str_dice():
    # STR 60 → 12 dice; boulder PD5 BODY13 → cap 18 → not limiting → 12d6
    dice, dtype = resolve_object_throw(thrower_str=60, pd=5, body=13, damage_type="normal")
    assert dice == 12


def test_str60_lamppost_capped():
    # STR 60 → 12 dice; lamppost PD5 BODY3 → cap 8 → 8d6
    dice, dtype = resolve_object_throw(thrower_str=60, pd=5, body=3, damage_type="normal")
    assert dice == 8


def test_sharp_object_is_killing():
    dice, dtype = resolve_object_throw(thrower_str=30, pd=2, body=4, damage_type="killing")
    assert dtype == "killing"


def test_str_zero_yields_zero_dice():
    dice, dtype = resolve_object_throw(thrower_str=0, pd=5, body=10, damage_type="normal")
    assert dice == 0


def test_zero_pd_zero_body_yields_zero_dice():
    dice, dtype = resolve_object_throw(thrower_str=40, pd=0, body=0, damage_type="normal")
    assert dice == 0
