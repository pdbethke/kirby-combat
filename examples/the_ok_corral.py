"""The Gunfight at the O.K. Corral --- 26 October 1881, Tombstone.

THE COMBAT BENCHMARK. Nine real HERO builds, real HSEG weapon prefabs, on
the real lot beside Fly's. Nothing here is hand-rolled: the characters come
through the canon HDCLoader and the guns are the prefabs' own costed
objects.

WHY A HISTORICAL GUNFIGHT IS A GOOD TEST. It measures two things at once ---
how long the fight lasts, and what gets CHOSEN --- and both are falsifiable
against something outside the engine. A fight that ends in seven Phases, or
one where every Phase picks the same maneuver, is the engine telling you
something is mispriced. Runs through 2026-09-07 went 7 -> 13 -> 24 -> 41
Phases as three defects came out, and the mix went from 11-of-13 Multiple
Attacks to a real spread:

  1. MINUSONEPIP was skipped when reading damage dice. Its alias is
     "+1d6 -1" --- the 2d6-1 rung --- so skipping it drops most of a die.
     The Colt Peacemaker is RKA LEVELS=1 + MINUSONEPIP, five of the nine
     men carried one, and the Earps were firing at 1d6 against 2d6.
  2. Multiple Attack charged a DESCENDING OCV ladder, which made its first
     shot identical to attacking once and every further shot free. 6E2
     p.73 charges (N-1) x -2 on every roll. The picker spamming it was
     correct behaviour against a broken price.
  3. A miss did not end the sequence (6E2 p.73 says it does).

WHAT THIS BENCHMARK CANNOT TEST: cover. The lot has buildings on both
flanks and the two lines stood about 2m apart, so `cover_available`
returns no reachable cover for anybody --- correctly. Zero cover-taking
here is the right answer, not a failure, and proving that work needs a map
with crossable obstacles.

WHAT IT NEEDS. Two directories of licensed material this repo does not and
will not ship, named by environment variable:

    KIRBY_WESTERN_HDC     .hdc archetypes (Lawman, Gunfighter, Gambler...)
    KIRBY_HSEG_PREFABS    .hdp nineteenth-century weapon prefabs
    KIRBY_COST_HDT        a HERO Designer .hdt --- kirby-cost needs it

Without them the script says so and exits cleanly, which is what lets it
sit in `examples/` and be executed by the suite like every other script
here.

By default every Phase is chosen by `TacticChooser`, which is
deterministic and needs nothing external. The benchmark proper drives the
same encounter from a chooser that asks a language model instead; that
seat lives outside this repo, and `--seat` names it.
"""
import glob
import os
import pathlib
import sys
from dataclasses import replace

from kirby_combat.encounter import Encounter
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop import Roster, TacticChooser, run_encounter
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_cost.io.hdc_loader import HDCLoader
from kirby_dice import RandomRoller

#: Where the archetypes and the weapon prefabs live on THIS machine. Both
#: are paid Hero Games material, so the repo carries the variable names and
#: never the files --- and a machine-bound literal path here would put the
#: suite back to being unrunnable anywhere but one laptop.
WESTERN = os.environ.get("KIRBY_WESTERN_HDC")
HSEG = os.environ.get("KIRBY_HSEG_PREFABS")

#: Historical armament. The Earps carried revolvers; Doc Holliday carried a
#: coach gun, which is why he is the most dangerous man on the lot.
LAWMEN = [("Wyatt Earp", "Lawman", ["Colt Peacemaker"]),
          ("Virgil Earp", "Lawman", ["Colt Peacemaker"]),
          ("Morgan Earp", "Lawman", ["Colt Peacemaker"]),
          ("Doc Holliday", "Gambler", ["Shotgun", "Colt Peacemaker"])]

# Two of the five Cowboys were UNARMED, and arming them is what made this
# benchmark unwinnable for the Earps. Ike Clanton --- who had spent the
# night threatening them --- was carrying nothing when it started; Wyatt
# told him so and let him go, and he ran into Fly's. Billy Claiborne ran
# with him. Nine men stood in the lot and seven guns were among them.
#
# Handing the pair a Peacemaker each looked like rounding the roster up. It
# is two extra shooters on the side that already had the better rifles, and
# the Cowboys swept every run before it was corrected. An empty list is the
# historical fact and the harder test: an unarmed man in a crossfire is
# exactly the actor who ought to be running.
COWBOYS = [("Billy Clanton", "Gunfighter", ["Colt Frontier .44-40"]),
           ("Frank McLaury", "Skilled Gunfighter", ["Colt Frontier .44-40"]),
           ("Tom McLaury", "Cowboy", ["Winchester '73"]),
           ("Ike Clanton", "Cowboy", []),
           ("Billy Claiborne", "Cowboy", [])]


def the_lot() -> Scene:
    """The vacant lot beside Fly's, 26 October 1881, about 3pm.

    Laid out from the contemporary map of Tombstone: the lot runs south
    from Fremont Street between the HARWOOD HOUSE on the west and C.S.
    FLY'S LODGINGS on the east, with FLY'S STUDIO closing the south-east.
    It is about 5.5m across -- the fight did not happen in the O.K. Corral
    at all, but in this gap beside it.

    The nine men stood in two facing lines roughly two metres apart, which
    is the single most important fact about the gunfight: at that range
    nobody misses for long, and every melee offer in the engine is gated
    out because 6E2 p.56 puts Reach at one metre. They could shoot each
    other but not punch each other, and the numbers say so.

    Positions are the map's own, north to south:
        Doc Holliday at the mouth; then Tom McLaury / Morgan Earp,
        Frank McLaury / Wyatt Earp, Ike Clanton / Virgil Earp facing off
        down the lot; Billy Clanton furthest in on the Harwood side, and
        Billy Claiborne -- who ran -- nearest Fly's Studio.
    """
    WEST, EAST = 1.5, 3.5          # the two firing lines, 2m apart
    return Scene(
        id="fly-lot", name="Vacant lot beside Fly's Boarding House",
        bounds=SceneBounds(-2.0, -2.0, 0.0, 8.0, 12.0, 12.0),
        surfaces=[Surface(
            id="lot-ground", name="Hard-packed dirt",
            polygon_xy=[(0.0, 0.0), (5.5, 0.0), (5.5, 10.0), (0.0, 10.0)],
            elevation_m=0.0, surface_type="ground", cover_level=0,
        )],
        walls=[
            Wall(id="harwood", name="Harwood House (west wall)",
                 segment=(Position(0.0, 0.0, 0.0), Position(0.0, 10.0, 0.0)),
                 height_m=6.0, blocks_los=True, blocks_movement=True,
                 cover_level=4, body=8, def_value=4, climb_difficulty=-3),
            Wall(id="flys-lodgings", name="C.S. Fly's Lodgings (east wall)",
                 segment=(Position(5.5, 2.5, 0.0), Position(5.5, 10.0, 0.0)),
                 height_m=6.0, blocks_los=True, blocks_movement=True,
                 cover_level=4, body=8, def_value=4, climb_difficulty=-3),
            Wall(id="flys-studio", name="C.S. Fly's Studio (south-east)",
                 segment=(Position(5.5, 0.0, 0.0), Position(5.5, 2.0, 0.0)),
                 height_m=5.0, blocks_los=True, blocks_movement=True,
                 cover_level=4, body=8, def_value=4, climb_difficulty=-3),
            # A photographer's wagon stood at the lot's mouth on Fremont.
            # Low: something to drop behind, not something to hide inside.
            Wall(id="wagon", name="Photographer's wagon",
                 segment=(Position(1.0, 9.5, 0.0), Position(4.5, 9.5, 0.0)),
                 height_m=1.5, blocks_los=False, blocks_movement=True,
                 cover_level=2, body=6, def_value=2, climb_difficulty=0),
        ],
        hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={
            "doc_holliday":   Position(2.5, 8.5, 0.0),   # 1, at the mouth
            "tom_mclaury":    Position(WEST, 7.0, 0.0),  # 2
            "morgan_earp":    Position(EAST, 7.0, 0.0),  # 3
            "frank_mclaury":  Position(WEST, 5.5, 0.0),  # 4
            "wyatt_earp":     Position(EAST, 5.5, 0.0),  # 5
            "ike_clanton":    Position(WEST, 4.0, 0.0),  # 6
            "virgil_earp":    Position(EAST, 4.0, 0.0),  # 7
            "billy_clanton":  Position(WEST, 2.5, 0.0),  # 8
            "billy_claiborne": Position(EAST, 1.0, 0.0), # 9, who ran
        },
    )


def arsenal() -> dict:
    """Every 19th-century weapon HSEG defines, by name."""
    out = {}
    for path in sorted(glob.glob(os.path.join(HSEG, "*.hdp"))):
        for e in getattr(HDCLoader().load_file(path), "equipment", []) or []:
            out.setdefault(getattr(e, "name", "") or "", e)
    return out


def arm(name: str, archetype: str, weapons: list, side: Side, guns: dict):
    """Load an archetype and hand it its guns.

    The weapon objects are the HSEG prefab's own -- costed by the engine,
    not rebuilt here -- appended to the character's equipment, which
    `HeroCombatant.attacks` now reads.
    """
    c = HeroCombatant.from_hdc(os.path.join(WESTERN, f"{archetype}.hdc"), id=name.lower().replace(" ", "_"))
    c.hero.equipment = list(getattr(c.hero, "equipment", None) or []) + [guns[w] for w in weapons]
    c.hero.name = name
    return replace(c, side=side)


def _seat(name: str, roster: dict):
    """The chooser that decides each Phase.

    `tactics` is the deterministic seat and the default, so this script
    runs anywhere the character files do. Any other name is imported by
    `module:factory`, called with the roster, and used as-is --- which is
    how the benchmark proper attaches a chooser backed by a language model
    without this repo depending on one.
    """
    if name == "tactics":
        return TacticChooser()
    module_name, _, factory = name.partition(":")
    if not factory:
        raise SystemExit(f"--seat wants 'module:factory', got {name!r}")
    import importlib

    return getattr(importlib.import_module(module_name), factory)(roster)


def main() -> None:
    seat_name = "tactics"
    for i, arg in enumerate(sys.argv[1:]):
        if arg.startswith("--seat="):
            seat_name = arg.split("=", 1)[1]

    if not WESTERN or not HSEG:
        print("The O.K. Corral needs two directories of licensed material "
              "this repo does not ship.")
        print("  KIRBY_WESTERN_HDC   -- .hdc archetypes")
        print("  KIRBY_HSEG_PREFABS  -- .hdp weapon prefabs")
        print("Set both (and KIRBY_COST_HDT) to run the benchmark. "
              "Nothing to do; exiting cleanly.")
        return

    guns = arsenal()
    print(f"HSEG arsenal loaded: {len(guns)} nineteenth-century weapons\n")

    law, cow = Side.named("Earps"), Side.named("Cowboys")
    fighters = ([arm(n, a, w, law, guns) for n, a, w in LAWMEN]
                + [arm(n, a, w, cow, guns) for n, a, w in COWBOYS])
    scene = the_lot()

    print("THE GUNFIGHT AT THE O.K. CORRAL -- in the lot")
    for c in fighters:
        st = c.combat_stats()
        print(f"  {c.hero.name:<15} [{Side.of(c).name:<8}] OCV {st.ocv} "
              f"DCV {st.dcv} SPD {st.spd} STUN {c.state.current_stun:>3} | "
              f"{', '.join(a.name for a in c.attacks) or 'unarmed'}")
    print(f"\n  The lot: {scene.name}")
    print(f"    {len(scene.walls)} walls, "
          f"opening range 2m between the front men\n")

    roller = RandomRoller(seed=18811026)
    session = CombatSession.create(
        id="ok-corral", combatants=fighters, scene=scene,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=roller).start()
    result = run_encounter(
        Encounter(id="tombstone", turn=1, segment=12, sessions=[session]),
        _seat(seat_name, {c.id: c for c in fighters}),
        roller=roller, on_unresolvable="skip", max_turns=40)

    print(f"  decided: {result.complete}  winner: {result.winner}  "
          f"phases: {result.phases}")
    if result.skipped_kinds:
        print(f"  skipped: {result.skipped_kinds}")
    print()
    for c in result.encounter.sessions[0].combatants.values():
        state = "DOWN" if c.is_ko or c.state.current_body <= 0 else "up"
        print(f"  {c.hero.name:<15} STUN {c.state.current_stun:>4} "
              f"BODY {c.state.current_body:>3}  {state}")
    print("\n  standing:",
          {s.name: len(v)
           for s, v in Roster(result.encounter.sessions[0]).standing.items()})


if __name__ == "__main__":
    main()
