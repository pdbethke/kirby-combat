"""The house, and the base — a Scene at rest, a Scene keeping time.

6E2 p.8, "COMBAT AND NONCOMBAT TIME": "Unless it looks like there's going
to be a fight (or some other sequence you need to detail precisely, like
a car chase), you don't have to be exact about things like time or
distance." Most of a campaign is NOT combat. Five people cooking dinner
and doing chores in a house is a perfectly ordinary scene, and it needs
none of a HERO Turn's machinery to be complete.

This example builds one Campaign, one World, and TWO Scenes in it:

  The house -- five occupants placed, going about their day. It has NO
  Encounter at all (`scene.encounter is None`). There is no Turn to be
  on, no Segment to advance, nothing that can tick a clock. That is not
  a hole in the model -- it is the resting state 6E2 p.8 describes, and
  this example's whole point is to show it is a complete, valid Scene on
  its own, not a stub waiting for combat to fill it in.

  The base -- a Scene where a fight (or at least something that needs
  Segment-level accounting) is underway, so it carries an Encounter.
  Combat begins on Segment 12 (6E2 p.20, "BEGINNING COMBAT"), which is
  why `Encounter.segment` defaults to 12; a Turn is 12 Segments (6E2
  p.18, "SEGMENT"), so advancing the clock past Segment 12 wraps to
  Segment 1 of the next Turn. `Encounter.advance_segment()` is exercised
  here to show that wrap happening.

Same World, same hierarchy, two different scenes -- the only thing that
distinguishes "a fight" from "five people doing chores" is whether that
one field, `encounter`, is set. Precise time is something a GM switches
ON for a scene that needs it; it is not the default state of a place.

Exercises:
  - Campaign, World, World.scene_by_id
  - Scene.place_combatant (five placements, no Encounter)
  - Encounter, Encounter.advance_segment (Segment 12 -> Turn 2, Segment 1)

No dependencies beyond the package.

Run with:
    .venv/bin/python examples/the_house.py
"""
from __future__ import annotations

from dataclasses import replace

from kirby_combat.campaign import Campaign
from kirby_combat.encounter import Encounter
from kirby_combat.scene import AmbientConditions, Position, Scene, SceneBounds
from kirby_combat.world import World


def rule(title: str) -> None:
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


def describe(scene: Scene) -> None:
    print(f"  Scene {scene.id!r} ({scene.name})")
    if scene.encounter is None:
        print("    encounter: None -- no Turn, no Segment, nothing ticking.")
        print("    (6E2 p.8: this is the normal resting state of a place.)")
    else:
        enc = scene.encounter
        print(f"    encounter: Turn {enc.turn}, Segment {enc.segment}")
    if scene.combatant_positions:
        print("    occupants:")
        for combatant_id, pos in scene.combatant_positions.items():
            print(f"      {combatant_id:10} at ({pos.x:.0f}, {pos.y:.0f}, {pos.z:.0f})")


def main() -> None:
    rule("THE HOUSE, AND THE BASE — one World, two kinds of scene")

    # ── 1. Build the World with two empty scenes ─────────────────────────────
    house_bounds = SceneBounds(0, 0, 0, 20, 15, 4)
    house = Scene(
        id="house", name="The Whitfield house",
        bounds=house_bounds,
        surfaces=[],
        walls=[],
        hazards=[],
        ambient=AmbientConditions(),
        # No `encounter` argument at all -- it defaults to None. This is
        # the headline: a Scene needs nothing else to be complete.
    )

    base_bounds = SceneBounds(0, 0, 0, 40, 40, 10)
    base = Scene(
        id="base", name="Arthon's forward base",
        bounds=base_bounds,
        surfaces=[],
        walls=[],
        hazards=[],
        ambient=AmbientConditions(),
        encounter=Encounter(id="base-encounter"),  # Turn 1, Segment 12 (6E2 p.20)
    )

    world = World(id="haven-city", name="Haven City", scenes=[house, base])
    campaign = Campaign(id="campaign-1", name="Haven City Chronicles", worlds=[world])
    print(f"  Campaign {campaign.name!r} -> World {world.name!r} -> "
          f"{len(world.scenes)} scenes")

    # ── 2. The house — five occupants, no combat, no clock ───────────────────
    rule("1. The house — five occupants doing chores, no combat")

    occupants = {
        "grandmother": Position(2.0, 3.0, 0.0),
        "father":      Position(5.0, 8.0, 0.0),
        "mother":      Position(6.0, 8.0, 0.0),
        "teenager":    Position(9.0, 12.0, 0.0),
        "toddler":     Position(4.0, 5.0, 0.0),
    }
    for combatant_id, pos in occupants.items():
        house = house.place_combatant(combatant_id, pos)
    world = replace(world, scenes=[house, base])

    describe(house)
    print("\n  Five people, one place, nobody tracking Segments. That is the")
    print("  point -- this Scene is already complete. Nothing is missing.")

    # ── 3. The base — an Encounter is running, and the clock moves ───────────
    rule("2. The base — an Encounter IS running")
    describe(base)

    print("\n  Advancing the clock a few Segments:")
    for _ in range(3):
        new_encounter = base.encounter.advance_segment()
        base = replace(base, encounter=new_encounter)
        world = replace(world, scenes=[house, base])
        print(f"    Turn {new_encounter.turn}, Segment {new_encounter.segment}")

    print("\n  ...and driving it straight through the Segment 12 -> Turn+1 wrap:")
    encounter = base.encounter
    while encounter.segment < 12:
        encounter = encounter.advance_segment()
    print(f"    at Turn {encounter.turn}, Segment {encounter.segment} (12)")
    wrapped = encounter.advance_segment()
    print(f"    advance_segment() -> Turn {wrapped.turn}, Segment {wrapped.segment}")
    base = replace(base, encounter=wrapped)
    world = replace(world, scenes=[house, base])
    assert wrapped.turn == encounter.turn + 1 and wrapped.segment == 1

    rule("THE CONTRAST")
    print("  Same World. Same kind of Scene object. One field tells them apart:")
    print(f"    house.encounter is None : {house.encounter is None}")
    print(f"    base.encounter is None  : {base.encounter is None}")
    print("\n  A house at rest and a base under fire live in the same World,")
    print("  built from the same Scene class, told apart by nothing more than")
    print("  whether time is being counted precisely (6E2 p.8).")

    rule("END")


if __name__ == "__main__":
    main()
