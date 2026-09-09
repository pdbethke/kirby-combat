"""The Gunfight at the O.K. Corral --- 26 October 1881, Tombstone.

THE COMBAT BENCHMARK. Nine real HERO builds, real HSEG weapon prefabs, on
the real lot beside Fly's. Nothing here is hand-rolled: the characters come
through the canon loader at IMPORT time and the guns are the prefabs' own costed
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

COVER, AND A CLAIM THAT STOPPED BEING TRUE. This file used to say the lot
could not test cover: both buildings run PARALLEL to the firing lines and
outside them, so they are beside you and never in front, and
`cover_available` correctly returned nothing reachable. That was true of
the documented geography and it hid two real defects --- cover that
changed no to-hit number, and a cover level computed against the WORST
threat instead of per shooter. "The map explains it" is the shape to
distrust.

Three pieces of a working yard's ordinary clutter now stand BETWEEN the
lines (see `the_lot`), so men take cover here and the benchmark measures
it: eight cover picks in Turn 1, and under the deterministic seat a
fighter takes cover once and then fires from it.

WHAT IT NEEDS. One directory of BUILD DOCS for licensed material this repo
does not and will not ship, named by environment variable:

    KIRBY_CORRAL_BUILDS   <Archetype>.json + arsenal.json + PowerLad.json
    KIRBY_COST_HDT        a HERO Designer .hdt --- kirby-cost needs it

Build docs, not .hdc files, and that is not a detail. This engine reads no
HERO Designer files at all any more (2026-09-08): a character arrives as a
costed `LoadedHero`, and the parse happened ONCE, wherever the import was
done. Re-parsing HDC every run meant the benchmark that measures combat
quality never touched the canonical costed shape the product rests on. Write
the docs with `kirby_cost.io.build_json.to_build_json`; read them back with
`build_from_json`, which is all this file does.

Without them the script says so and exits cleanly, which is what lets it
sit in `examples/` and be executed by the suite like every other script
here.

By default every Phase is chosen by `TacticChooser`, which is
deterministic and needs nothing external. The benchmark proper drives the
same encounter from a chooser that asks a language model instead; that
seat lives outside this repo, and `--seat` names it.
"""
import json
import os
import pathlib
import sys
from dataclasses import replace

from kirby_combat.encounter import Encounter
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop import Roster, TacticChooser, run_encounter
from kirby_combat.scene.construct import Construct
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_cost.io.build_json import build_from_json
from kirby_dice import RandomRoller

#: Where the archetypes and the weapon prefabs live on THIS machine. Both
#: are paid Hero Games material, so the repo carries the variable names and
#: never the files --- and a machine-bound literal path here would put the
#: suite back to being unrunnable anywhere but one laptop.
#: A directory of build docs: one per archetype, plus `arsenal.json` whose
#: equipment list is every 19th-century weapon HSEG defines. `PowerLad.json`
#: alongside them arms `--power-lad`.
BUILDS = os.environ.get("KIRBY_CORRAL_BUILDS")

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

    Four of the seven features are the lot's documented geography. Three
    -- barrels, a trough, packing crates -- are a working yard's ordinary
    clutter, added deliberately: the geography alone gives nobody cover,
    because both buildings run parallel to the firing lines and outside
    them. See the note beside them.

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
            # THE BOOK'S OWN NUMBERS. 6E2 p.173's Objects Table: a Home
            # outside wall is PD 4 / ED 6 / BODY 3. These were BODY 8, and
            # p.172's worked example says what a wall's BODY actually buys
            # --- Chiron chops a 5 PD, 6 BODY wall and it is "damaged but
            # still standing; another good blow will cut THROUGH it
            # easily". That is a HOLE, not a demolition.
            #
            # `part_of` names the building each is a face of, so running
            # the BODY out breaches the wall instead of levelling the
            # house. The structure's own BODY is on the interiors below.
            Wall(id="harwood", name="Harwood House (west wall)",
                 segment=(Position(0.0, 0.0, 0.0), Position(0.0, 10.0, 0.0)),
                 height_m=6.0, blocks_los=True, blocks_movement=True,
                 cover_level=4, body=3, def_value=4, ed_value=6,
                 part_of="harwood-interior", climb_difficulty=-3),
            Wall(id="flys-lodgings", name="C.S. Fly's Lodgings (east wall)",
                 segment=(Position(5.5, 2.5, 0.0), Position(5.5, 10.0, 0.0)),
                 height_m=6.0, blocks_los=True, blocks_movement=True,
                 cover_level=4, body=3, def_value=4, ed_value=6,
                 part_of="flys-interior", climb_difficulty=-3),
            Wall(id="flys-studio", name="C.S. Fly's Studio (south-east)",
                 segment=(Position(5.5, 0.0, 0.0), Position(5.5, 2.0, 0.0)),
                 height_m=5.0, blocks_los=True, blocks_movement=True,
                 cover_level=4, body=3, def_value=4, ed_value=6,
                 part_of="flys-interior", climb_difficulty=-3),
            # A photographer's wagon stood at the lot's mouth on Fremont.
            # Low: something to drop behind, not something to hide inside.
            # 6E2 p.173: Wagon, covered --- PD 3 / ED 2 / BODY 12. A wagon
            # is a solid thing to shelter behind and takes real work to
            # break, which is the opposite of a wall.
            Wall(id="wagon", name="Photographer's wagon",
                 segment=(Position(1.0, 9.5, 0.0), Position(4.5, 9.5, 0.0)),
                 height_m=1.5, blocks_los=False, blocks_movement=True,
                 cover_level=2, body=12, def_value=3, ed_value=2,
                 climb_difficulty=0),

            # ---- SET DRESSING, and it changes the fight ----
            #
            # The four features above are the lot's documented geography.
            # These three are a working yard's ordinary clutter, and they
            # are here because the geography alone offers NOBODY any cover.
            #
            # WHY THE BUILDINGS DO NOT COUNT. Cover means putting a thing
            # between you and the man shooting at you. Harwood House and
            # Fly's run NORTH-SOUTH, parallel to both firing lines and
            # OUTSIDE them, so a Cowboy pressed against Harwood still has
            # every Earp in clear view -- the wall is beside him, not in
            # front. `cover_available` says so, correctly, and returns 0.
            # And the far side of a building, where cover does exist, is
            # not reachable: `movement_reach` clamps toward a destination
            # rather than pathfinding around a wall's end.
            #
            # A barrel is different in the one way that matters: it is
            # SMALL and it sits BETWEEN the lines, so its covered side is
            # the side you are already standing on. These run north-south
            # across the middle of the lot at x ~ 2.3-3.0, which is where
            # a line from a Cowboy to an Earp crosses.
            Wall(id="barrels", name="Stack of whiskey barrels",
                 segment=(Position(2.3, 2.8, 0.0), Position(2.3, 3.6, 0.0)),
                 height_m=1.2, blocks_los=False, blocks_movement=True,
                 cover_level=2, body=4, def_value=2, climb_difficulty=0),
            Wall(id="trough", name="Water trough",
                 segment=(Position(3.0, 5.0, 0.0), Position(3.0, 6.2, 0.0)),
                 height_m=0.8, blocks_los=False, blocks_movement=True,
                 cover_level=2, body=5, def_value=3, climb_difficulty=0),
            Wall(id="crates", name="Packing crates",
                 segment=(Position(2.6, 7.2, 0.0), Position(2.6, 8.0, 0.0)),
                 height_m=1.5, blocks_los=False, blocks_movement=True,
                 cover_level=3, body=4, def_value=2, climb_difficulty=0),
        ],
        hazards=[], ambient=AmbientConditions(light_level=4),
        # THINGS A STRONG MAN CAN PICK UP. The lot's barrels and crates are
        # `Wall`s --- geometry that blocks and grants cover --- so nothing in
        # it was ever a thing you could lift. A freight wagon parked at the
        # mouth is: 6 BODY, about a tonne by the engine's mass proxy, well
        # inside a STR 40 lift of 6,400kg and far beyond any of the nine men.
        #
        # It changes nothing for them and gives a brick his signature move,
        # which is the point of putting one in a benchmark.
        constructs=[
            # THE BUILDINGS HAVE INSIDES. Their walls (above) are the faces
            # that front the lot; the buildings themselves stand behind
            # them --- Harwood House to the west, Fly's to the east. A
            # footprint is what lets the engine tell a man sheltering IN
            # one from a man leaning on it, which is what decides who a
            # collapse lands on.
            #
            # Ike Clanton and Billy Claiborne both ran into Fly's, which
            # is the whole reason this distinction is in the benchmark.
            Construct(
                obj_id="harwood-interior", kind="wall",
                segment=(Position(0.0, 0.0, 0.0), Position(0.0, 10.0, 0.0)),
                polygon_xy=[(-2.0, 0.0), (0.0, 0.0), (0.0, 10.0), (-2.0, 10.0)],
                elevation_range_m=(0.0, 6.0),
                height_m=6.0, blocks_los=True, blocks_movement=True,
                # THE STRUCTURE, not a face of it. A JUDGEMENT, and the
                # book has no building entry to cite --- but it does scale
                # its largest objects (Truck or bus BODY 17, Tank BODY 19,
                # large Spaceship BODY 30-80), and a two-storey timber
                # boarding house belongs with those and not with a BODY 3
                # wall panel. DEF 8 is the frame rather than the cladding:
                # above a Brick wall's PD 5 and a Concrete wall's PD 6.
                #
                # The point of the number: a Colt Peacemaker (2d6-1, 6
                # BODY average) does NOTHING to it, so no pistol levels a
                # building however long it fires. Shooting the WALL still
                # works and makes a hole.
                cover_level=4, def_value=8, body=30,
            ),
            Construct(
                obj_id="flys-interior", kind="wall",
                segment=(Position(5.5, 0.0, 0.0), Position(5.5, 10.0, 0.0)),
                polygon_xy=[(5.5, 0.0), (8.0, 0.0), (8.0, 10.0), (5.5, 10.0)],
                elevation_range_m=(0.0, 6.0),
                height_m=6.0, blocks_los=True, blocks_movement=True,
                cover_level=4, def_value=8, body=30,   # see Harwood, above
            ),
            Construct(
            obj_id="freight-wagon", kind="wall", portable=True,
            segment=(Position(3.0, 1.0, 0.0), Position(3.0, 1.0, 0.0)),
            height_m=1.6, blocks_los=False, blocks_movement=False,
            cover_level=2, def_value=3, body=6,
        )],
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


def _doc(name: str) -> dict:
    """One build doc from the configured directory."""
    with open(os.path.join(BUILDS, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def arsenal() -> dict:
    """Every 19th-century weapon HSEG defines, by name.

    One document carrying them all as EQUIPMENT --- which the build doc
    could not represent until 2026-09-08, so a carried weapon round-tripped
    into nothing and an armed man arrived unarmed.
    """
    out = {}
    for e in getattr(build_from_json(_doc("arsenal")), "equipment", []) or []:
        out.setdefault(getattr(e, "name", "") or "", e)
    return out



def the_sides():
    """The two sides, and what each was in that lot to do.

    Shared by the example and by `scripts/telemetry.py`, because a
    benchmark whose sides want different things from the demo's is not
    measuring the demo.
    """
    # WHAT EACH SIDE WANTED, which is the history and not a flavour note.
    # Virgil Earp was Tombstone's chief of police and went into that lot
    # to enforce the ordinance against carrying firearms in town: the
    # errand was to DISARM the Cowboys. Ike Clanton and Billy Claiborne,
    # both unarmed, ran -- which is what the Cowboys' objective says and
    # what the benchmark's withdrawals have always been doing without
    # anything on the page to explain them.
    #
    # PeterB: "virgil's goal should be kill the cowboys" -- "not shoot
    # buildings". The second half is the point; the first is softened to
    # the historical errand, which constrains a chooser more usefully
    # than "kill them" and is what the marshal was actually there for.
    law = Side.named(
        "Earps",
        objective=("Disarm the Cowboys and place them under arrest. "
                   "Shoot the men, not the buildings."),
    )
    cow = Side.named(
        "Cowboys",
        objective=("Do not be disarmed. Fight your way clear of the lot, "
                   "and get the unarmed men out."),
    )
    return law, cow

def arm(name: str, archetype: str, weapons: list, side: Side, guns: dict):
    """Load an archetype and hand it its guns.

    The weapon objects are the HSEG prefab's own -- costed by the engine,
    not rebuilt here -- appended to the character's equipment, which
    `HeroCombatant.attacks` now reads.
    """
    c = HeroCombatant.from_build(build_from_json(_doc(archetype)),
                                 id=name.lower().replace(" ", "_"))
    c.hero.equipment = list(getattr(c.hero, "equipment", None) or []) + [guns[w] for w in weapons]
    c.hero.name = name
    return replace(c, side=side)


#: Where he lands: the lot's CLOSED end, between the two lines. Doc
#: Holliday is at the mouth (y 8.5) and the deep end is y 0, so this is
#: the direction both unarmed Cowboys run --- which is the point. A man
#: standing in the only way out changes what "get clear" means for
#: everyone, and `disengage` reads the enemies' centroid, not a door.
POWER_LAD_AT = (2.5, 0.5)


def the_interloper():
    """Power Lad, 399.5 points, in a gunfight between men worth about 75.

    NOT historical and not pretending to be --- the benchmark's value is
    that everything else in the lot is real, so an anachronism dropped
    into it is measured against a fight we know the shape of. He is his
    OWN side (`Side.solo`): the Earps and the Cowboys go on shooting each
    other, and he is everybody's problem. `Roster` already treats a side
    of one as the free-for-all case, so this needs no new rule --- it
    exercises one the benchmark has never reached, because the Corral has
    only ever had two sides.

    Returns None when his build doc is not there, so the fight is the
    historical one and the script still runs anywhere.
    """
    if not BUILDS or not os.path.exists(os.path.join(BUILDS, "PowerLad.json")):
        print("--power-lad wants PowerLad.json beside the other builds;"
              " not there, so the lot stays historical.\n")
        return None
    c = HeroCombatant.from_build(build_from_json(_doc("PowerLad")), id="power_lad")
    c.hero.name = "Power Lad"
    return replace(c, side=Side.solo("power_lad"))


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
    interloper = False
    for i, arg in enumerate(sys.argv[1:]):
        if arg.startswith("--seat="):
            seat_name = arg.split("=", 1)[1]
        elif arg == "--power-lad":
            interloper = True

    if not BUILDS or not os.path.isdir(BUILDS):
        print("The O.K. Corral needs build docs for licensed material this "
              "repo does not ship.")
        print("  KIRBY_CORRAL_BUILDS -- a directory of <Archetype>.json "
              "plus arsenal.json")
        print("Set it (and KIRBY_COST_HDT) to run the benchmark. "
              "Nothing to do; exiting cleanly.")
        return

    guns = arsenal()
    print(f"HSEG arsenal loaded: {len(guns)} nineteenth-century weapons\n")

    law, cow = the_sides()
    fighters = ([arm(n, a, w, law, guns) for n, a, w in LAWMEN]
                + [arm(n, a, w, cow, guns) for n, a, w in COWBOYS])
    scene = the_lot()

    if interloper:
        lad = the_interloper()
        if lad is not None:
            fighters.append(lad)
            scene = replace(scene, combatant_positions={
                **scene.combatant_positions,
                "power_lad": Position(POWER_LAD_AT[0], POWER_LAD_AT[1], 0.0),
            })

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
