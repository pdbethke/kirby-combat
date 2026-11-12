"""Kerendor divides his Multipower — 6E1 p.404-406, reproduced.

This is a conformance check that happens to be readable: the rulebook's own
worked example is restated below, the engine is driven through it, and every
number the book states is ASSERTED against what the engine produced. If the
engine ever stops agreeing with the book, this script exits non-zero.

THE BOOK'S SCENARIO (6E1 p.406, Kerendor), PARAPHRASED — this project ships
no rules text; open your own copy:

    Kerendor owns a Multipower whose reserve is 60 points. Its variable
    slots are an Energy Blast, a Flight and a Resistant Protection (15 PD /
    15 ED, which is 45 Active Points). Each turn he divides the reserve as
    he likes among the slots, and each slot then has as many LEVELS as the
    points it holds will buy:

      * 30 into Blast and 30 into Flight: a 6d6 Blast and 30m of Flight.
      * 40 into Flight and 20 into Blast: 40m of Flight and a 4d6 Blast.
      * Resistant Protection switched on takes its 45; the 15 left buy
        either 15m of Flight or a 3d6 Blast.
      * With all three variable: 10 into Flight, 40 into Blast and 9 into
        Protection gives 10m of Flight, an 8d6 Blast and 3 PD / 3 ED.
      * Advantages count. 30 points put into a Flight bought at 50m with a
        +1/4 Advantage (Reduced Endurance) buy 24m, not 30: the slot's
        points pay for the Advantage as well.

WHY THIS EXAMPLE IS WORTH A SCRIPT. Every number is read from the engine's
REAL views (`attacks`, `movement_view`, `defense_view`) after a split is
stated; nothing here prices anything. The pricing is kirby-cost's
(`levels_within`), and what this page proves is that the combat engine
reaches it for attacks, movement AND defences alike, and that a slot holding
no points is off.

Needs a HERO Designer template to cost the slots against:

    KIRBY_COST_HDT   a HERO Designer .hdt --- kirby-cost needs it

Without it the script says so and exits cleanly, like the other examples
that need licensed material.

Run with:
    .venv/bin/python examples/raw_kerendor_multipower.py
"""
from __future__ import annotations

import os
from dataclasses import replace

#: The slots, by NAME: a build doc's ids are renumbered on load.
BLAST, FLIGHT, RP, ADV = "Blast", "Flight", "Resistant Protection", "Efficient Flight"
FRAMEWORK = "MP"          # the id this doc gives the reserve; renumbered too
_CHARS = [{"xmlid": x, "levels": 0} for x in (
    "STR", "DEX", "CON", "BODY", "STUN", "END", "SPD", "PD", "ED", "REC", "OCV", "DCV")]


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


def kerendor():
    from kirby_cost.io.build_json import build_from_json
    from kirby_cost.services.power_builder import build_power_from_spec

    from kirby_combat.hero_view import HeroCombatant

    build = build_from_json({
        "name": "Kerendor", "template": "Main6E",
        "base_points": 400, "disad_points": 75, "experience": 0,
        "characteristics": _CHARS,
        "powers": [
            {"id": FRAMEWORK, "xmlid": "MULTIPOWER", "name": "Kerendor",
             "base_cost": 60.0},
            {"id": BLAST, "xmlid": "ENERGYBLAST", "name": "Blast", "levels": 12,
             "input": "ED", "parent": FRAMEWORK,
             "ultra_slot": False},
            {"id": FLIGHT, "xmlid": "FLIGHT", "name": "Flight", "levels": 60,
             "parent": FRAMEWORK, "ultra_slot": False},
            # (ultra_slot False = a Variable slot.)
            # Flight bought at 50m with +1/4 (Reduced Endurance).
            {"id": ADV, "xmlid": "FLIGHT", "name": "Efficient Flight",
             "levels": 50, "parent": FRAMEWORK, "ultra_slot": False,
             "modifiers": [{"id": "re", "xmlid": "REDUCEDEND",
                            "option_id": "HALFEND"}]},
        ],
        "skills": [], "perks": [], "talents": [], "disadvantages": [],
    })
    # Resistant Protection 15 PD / 15 ED is a FORCEFIELD, which a build doc
    # cannot carry; kirby-cost builds it and the loader's link is restored.
    framework = next(p for p in build.powers if p.xmlid == "MULTIPOWER")
    rp, _active, _real = build_power_from_spec(
        {"xmlid": "FORCEFIELD", "pd_levels": 15, "ed_levels": 15})
    rp.name, rp.parent = "Resistant Protection", framework
    rp.ultra = False                     # a VARIABLE slot
    rp._id = RP                          # the loader's id; read-only otherwise
    build.powers.append(rp)
    return HeroCombatant.from_build(build, id="kerendor")


def divide(hero, **points: int):
    """Kerendor after he states a split: the named slots hold the points,
    every other slot of the Multipower is off."""
    [mp] = hero.framework_view()
    ids = {s.name: s.slot_id for s in mp.slots}
    full = {sid: 0 for sid in ids.values()}
    full.update({ids[name]: pts for name, pts in points.items()})
    assert sum(full.values()) <= 60, full
    return replace(hero, state=replace(
        hero.state, slot_points={mp.framework_id: full}))


def blast_dice(hero) -> int:
    return sum(a.damage_dice for a in hero.attacks if a.xmlid == "ENERGYBLAST")


def flight_m(hero) -> float:
    return sum(m.combat_m for m in hero.movement_view() if m.mode == "flight")


def protection(hero) -> tuple[int, int]:
    return (sum(d.rpd for d in hero.defense_view() if d.name == RP),
            sum(d.red for d in hero.defense_view() if d.name == RP))


def main() -> None:
    if not os.environ.get("KIRBY_COST_HDT"):
        print("Kerendor's slots are costed against a HERO Designer template.")
        print("  KIRBY_COST_HDT -- a .hdt file")
        print("Set it to run this page. Nothing to do; exiting cleanly.")
        return

    hero = kerendor()

    rule("30 into Blast, 30 into Flight (6E1 p.406)")
    h = divide(hero, **{BLAST: 30, FLIGHT: 30})
    print(f"\n  Blast {blast_dice(h)}d6, Flight {flight_m(h):g}m")
    assert blast_dice(h) == 6 and flight_m(h) == 30.0
    print("  ok")

    rule("40 into Flight, 20 into Blast")
    h = divide(hero, **{FLIGHT: 40, BLAST: 20})
    print(f"\n  Flight {flight_m(h):g}m, Blast {blast_dice(h)}d6")
    assert flight_m(h) == 40.0 and blast_dice(h) == 4
    print("  ok")

    rule("Resistant Protection on (45): 15 left")
    h = divide(hero, **{RP: 45, FLIGHT: 15})
    print(f"\n  Protection {protection(h)}, Flight {flight_m(h):g}m, "
          f"Blast {blast_dice(h)}d6")
    assert protection(h) == (15, 15) and flight_m(h) == 15.0 and blast_dice(h) == 0
    h = divide(hero, **{RP: 45, BLAST: 15})
    print(f"  or Protection {protection(h)}, Flight {flight_m(h):g}m, "
          f"Blast {blast_dice(h)}d6")
    assert protection(h) == (15, 15) and flight_m(h) == 0.0 and blast_dice(h) == 3
    print("  ok")

    rule("All three variable: 10 / 40 / 9")
    h = divide(hero, **{FLIGHT: 10, BLAST: 40, RP: 9})
    print(f"\n  Flight {flight_m(h):g}m, Blast {blast_dice(h)}d6, "
          f"Protection {protection(h)}")
    assert flight_m(h) == 10.0 and blast_dice(h) == 8 and protection(h) == (3, 3)
    print("  ok")

    rule("Advantages count: 30 into Flight 50m with +1/4 Reduced Endurance")
    h = divide(hero, **{ADV: 30})
    print(f"\n  Flight {flight_m(h):g}m")
    assert flight_m(h) == 24.0
    print("  ok")

    rule("A slot holding nothing is off")
    h = divide(hero, **{BLAST: 60})
    assert flight_m(h) == 0.0 and protection(h) == (0, 0)
    assert blast_dice(h) == 12
    print("\n  Blast 12d6 and nothing else: ok")


if __name__ == "__main__":
    main()
