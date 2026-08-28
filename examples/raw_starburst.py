"""Starburst does a Move By — 6E2 p.72, where the book contradicts itself.

A conformance script, like `raw_andarra.py`, but for the harder case: this
page of the rulebook states a rule and then works an example that does not
follow it. The engine follows the RULE. This script asserts the rule's
numbers and prints the divergence, so anyone checking Kirby against the
book's example sees why the two differ and which one Kirby chose.

THE RULE AND THE EXAMPLE (6E2 p.72, "MOVE BY"), BOTH PARAPHRASED --
this project ships no rules text; open your own copy:

    THE RULE. A Move By does half the attacker's STR damage plus one d6 per
    10m of velocity. The page adds a parenthetical instruction: halve the
    character's STR BEFORE working out its damage, specifically so that
    nobody has to halve a half-die. The attacker takes one third of the
    damage done to the target.

    THE EXAMPLE, on the same page. A flying character with STR 15 and 30m of
    Flight Move Bys a villain from 10m away, ending 20m past him. The book
    computes the damage as (1/2 x 3d6) + 3d6 = 4 1/2d6.

WHY THEY DISAGREE. The parenthetical says to halve STR *before* converting to
damage: STR 15 -> 7 STR -> 7/5 = 1 DC, so 1 + 3 = 4 DC. The example instead
converts first and halves the dice: STR 15 -> 3d6, halved to 1 1/2d6, so
1 1/2 + 3 = 4 1/2d6. The parenthetical exists specifically to forbid that --
"that eliminates potential problems with trying to halve a half-die of
damage" -- and the example then halves a die anyway.

Kirby follows the rule. Distance past the target and the attacker's one-third
self-damage match the example exactly; only the STR half-step differs.
"""
import sys

from kirby_combat.actions.move_by import MoveBy

STR_, FLIGHT_M, DIST_TO_OGRE_M = 15, 30, 10

out = MoveBy.compute(
    attacker_str=STR_,
    velocity_mps=float(FLIGHT_M),
    total_movement_m=float(FLIGHT_M),
    distance_to_target_m=float(DIST_TO_OGRE_M),
)

rule_str_dc = (STR_ // 2) // 5          # halve STR FIRST, per the parenthetical
velocity_dc = FLIGHT_M // 10
rule_total_dc = rule_str_dc + velocity_dc

print("=" * 70)
print("  Starburst (STR 15, Flight 30m) Move Bys Ogre from 10m - 6E2 p.72")
print("=" * 70)
print(f"  velocity                 : {FLIGHT_M}m per Phase -> {velocity_dc} DC")
print(f"  STR, halved FIRST (rule) : {STR_} -> {STR_ // 2} STR -> {rule_str_dc} DC")
print(f"  engine damage_dc         : {out.damage_dc}")
print(f"  rule says                : {rule_total_dc} DC")
print()
print("  The example on the same page says 4 1/2d6, because it halves the")
print("  DICE (1/2 x 3d6 = 1 1/2d6) instead of halving STR first. The rule's")
print("  own parenthetical forbids exactly that. Kirby follows the rule.")
print()
print(f"  distance past target     : {out.distance_past_target_m:g}m   (example: 20m)")
print(f"  attacker self-damage     : {out.attacker_self_damage_fraction:.4f}   (example: one third)")
print("=" * 70)

# The rule's numbers are ASSERTED. The example's 4 1/2d6 is not, on purpose.
assert out.damage_dc == rule_total_dc == 4, (
    f"6E2 p.72 rule gives {rule_total_dc} DC; engine gave {out.damage_dc}"
)
assert out.distance_past_target_m == 20.0, out.distance_past_target_m
assert abs(out.attacker_self_damage_fraction - 1.0 / 3.0) < 1e-9

print("  Rule conformance confirmed: 4 DC, 20m past, one-third self-damage.")
print("=" * 70)
sys.exit(0)
