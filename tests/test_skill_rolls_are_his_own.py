"""A man's skill rolls are worked from HIS characteristics, whoever was built after him.

kirby-cost evaluates a skill's roll lazily against one global active hero
(`EngineContext`, the Java Hero Designer's single open character), and
`LoadedHero` says so: "Multi-hero consumers must re-set the active hero ...
before reading costs after any subsequent load." `HeroCombatant.skill_rolls`
read `roll_value` with whoever was loaded LAST active, so in a fight every
DEX- or INT-based skill rolled off the last-built man's characteristics. On
prod (fight a2caf042, 2026-11-01) every agent's Teamwork came out 11- where
his sheet says 12- or 13-; Stealth, Paramedics, Acrobatics and Breakfall
read the same door.
"""
from __future__ import annotations

from corpus import require_authored
from kirby_combat.hero_view import HeroCombatant


def test_his_roll_does_not_change_when_another_man_is_built():
    lad = HeroCombatant.from_build(require_authored("PowerLad"), id="lad")
    before = lad.skill_rolls()
    assert before, "PowerLad has roll-based skills"

    HeroCombatant.from_build(require_authored("Bokor"), id="bokor")

    assert lad.skill_rolls() == before
