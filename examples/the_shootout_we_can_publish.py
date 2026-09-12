"""The lot, the nine men, and numbers this repo is allowed to ship.

WHY THIS EXISTS BESIDE `the_ok_corral.py`. That benchmark loads build docs
for the archetypes and a 118-entry arsenal out of the HERO System
Equipment Guide --- paid Hero Games material, which is why it needs
`KIRBY_CORRAL_BUILDS` and refuses to run without it. A recording made from
it carries derived stat blocks and weapon damage, and PUBLISHING that
republishes the book.

So the cast here is AUTHORED, not imported. Nine historical people who
died before 1930, stats written for this file, revolvers written for this
file. Nothing traces to a book, the whole thing runs with no environment
variables and no template, and the recording it produces can go on a
public web page.

IT IS NOT A SUBSTITUTE FOR THE BENCHMARK. `the_ok_corral.py` measures the
engine against builds the cost engine produced; this measures nothing. It
is a show, and the numbers below are chosen to make a watchable one: real
6E shapes, ordinary human characteristics, revolvers that take three or
four hits to put a man down.

THE GROUND IS THE SAME LOT, imported from the benchmark rather than
copied, because the terrain is geometry we authored and carries no
licensed content.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kirby_combat.models import AttackPower, DefenseItem
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant


def revolver(name: str, dice: int = 2, *, minus_one: bool = True,
             charges: int = 6, range_m: float = 40.0) -> AttackPower:
    """A single-action revolver, written for this file.

    2d6-1 Killing is the ordinary shape for a heavy black-powder handgun
    in 6E terms and is what a reader would expect; it is not copied from
    any published weapon list. Six charges because that is how many
    chambers a Peacemaker has, which is history rather than a game stat.
    """
    return AttackPower(
        xmlid="RKA", name=name, damage_dice=dice, half_die=False,
        plus_one=False, minus_one=minus_one, damage_type="killing",
        defense_type="pd", range_m=range_m, uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        is_ranged=True, source_id=f"gun-{name.lower().replace(' ', '-')}",
        charges=charges, active_points=30,
    )


def shotgun() -> AttackPower:
    """Doc Holliday carried a coach gun into the lot; that is the one
    weapon detail here that is documented history rather than invention."""
    return AttackPower(
        xmlid="RKA", name="Coach gun", damage_dice=3, half_die=False,
        plus_one=False, damage_type="killing", defense_type="pd",
        range_m=15.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True,
        source_id="gun-coach", charges=2, active_points=45,
    )


def _man(cid: str, name: str, side: Side, *, dex: int, spd: int, ocv: int,
         dcv: int, stun: int, body: int, attacks=(), skills=None):
    """One ordinary man. No characteristic here is above the human maximum
    a 6E campaign would allow a competent gunfighter.

    BUILD-BACKED, because `enumerate_actions` refuses a flat stat block
    ("carries no `hero` to read powers and skills from") and every real
    build needs Hero Designer's licensed template. `synthetic_combatant`
    is the third way: a build-shaped combatant assembled from plain
    numbers, which is what lets this file ship.
    """
    return synthetic_combatant(
        id=cid, name=name, ocv=ocv, dcv=dcv, omcv=3, dmcv=3, spd=spd,
        dex=dex, ego=10, int_=10, str_=10, con=13, pre=13, rec=4,
        pd=2, ed=2, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=stun, max_body=body, max_end=25,
        current_stun=stun, current_body=body, current_end=25,
        side=side, attacks=list(attacks), skills=skills,
        # A long coat is not armour. One rPD so a graze is survivable and
        # a solid hit is not.
        defenses=[DefenseItem(name="Heavy coat", pd=1, rpd=1, is_resistant=True)],
        knockback_resistance=0,
    )


#: The two sides, with what each was in that lot to do. Virgil Earp was
#: Tombstone's chief of police and the errand was to enforce the ordinance
#: against carrying firearms in town.
def the_sides() -> tuple[Side, Side]:
    law = Side.named("Earps", objective=(
        "Disarm the Cowboys and place them under arrest. "
        "Shoot the men, not the buildings."))
    cow = Side.named("Cowboys", objective=(
        "Do not be disarmed. Fight your way clear of the lot, "
        "and get the unarmed men out."))
    return law, cow


def the_cast() -> list:
    """Nine men, in the positions the lot put them in.

    Ike Clanton and Billy Claiborne are unarmed because they were: both
    ran, and a benchmark that arms them is telling a different story.
    """
    law, cow = the_sides()
    return [
        _man("wyatt_earp", "Wyatt Earp", law, dex=14, spd=3, ocv=7, dcv=5,
             stun=26, body=11, attacks=[revolver("Colt revolver")]),
        _man("virgil_earp", "Virgil Earp", law, dex=13, spd=3, ocv=6, dcv=4,
             stun=26, body=11, attacks=[revolver("Colt revolver")]),
        _man("morgan_earp", "Morgan Earp", law, dex=13, spd=3, ocv=6, dcv=4,
             stun=24, body=10, attacks=[revolver("Colt revolver")]),
        # Doc Holliday was a dentist, which in HERO terms is Paramedics
        # -- and 6E2 p.109 makes that the roll that stops a man at 0 or
        # negative BODY bleeding to death. In a fight where three men go
        # down it is the most consequential thing on his sheet after the
        # coach gun.
        _man("doc_holliday", "Doc Holliday", law, dex=15, spd=3, ocv=7, dcv=5,
             stun=20, body=9, attacks=[shotgun(), revolver("Nickel revolver")],
             skills={"PARAMEDICS": 11}),
        _man("billy_clanton", "Billy Clanton", cow, dex=13, spd=3, ocv=6, dcv=4,
             stun=22, body=10, attacks=[revolver("Colt revolver")]),
        _man("frank_mclaury", "Frank McLaury", cow, dex=14, spd=3, ocv=6, dcv=5,
             stun=24, body=10, attacks=[revolver("Colt revolver")]),
        _man("tom_mclaury", "Tom McLaury", cow, dex=12, spd=3, ocv=5, dcv=4,
             stun=22, body=10, attacks=[revolver("Colt revolver")]),
        _man("ike_clanton", "Ike Clanton", cow, dex=11, spd=2, ocv=4, dcv=4,
             stun=20, body=10),
        _man("billy_claiborne", "Billy Claiborne", cow, dex=11, spd=2, ocv=4,
             dcv=4, stun=20, body=10),
    ]


#: The seed the public demo records, re-searched over 40 after the lot was
#: rebuilt to its real shape --- the geometry decides the fight, so the old
#: seed was chosen for a different place.
#:
#: CHOSEN FOR COVERAGE, NOT FOR HISTORY. The seed used to be picked so
#: the casualties matched 1881 --- three Cowboys down, Wyatt untouched ---
#: which is a fine thing for a museum and the wrong criterion for a
#: benchmark. The job of this fight is to FLEX the engine and show where
#: it is thin, so the seed is the one that exercises the most distinct
#: rule paths, measured over the first sixty.
#:
#: 59 reaches twenty of them: eight different Hit Locations including a
#: Head and a Vitals, both bleeding rules (6E2 p.109's bleed-out and
#: p.115's wound), Stunned, Knocked Out and Dying, a cover penalty, and a
#: shot whose Hit Location roll finds the cover instead of the man
#: (6E2 p.45). An Earp goes down, which history is clear did not happen
#: and which this file no longer optimises against.
#:
#: WHAT SIXTY SEEDS NEVER REACHED is the more useful half of the
#: measurement, and it is written down in `docs/gaps.md`.
DEMO_SEED = 59


#: Where each man stood when it started, in metres, with Fremont Street
#: running east-west along y = 0 and the lot running SOUTH from it.
#:
#: THE GROUND, as the inquest and the surveys have it. The vacant lot lay
#: between the Harwood house on the WEST and C.S. Fly's boarding house and
#: photograph gallery on the EAST, about eighteen feet across, opening
#: north onto Fremont. The Earps and Holliday came west along Fremont and
#: turned in at the mouth; the Cowboys were already in the lot. The whole
#: thing was fought at six to ten feet, which is the single most
#: surprising fact about it and the one a wide corridor destroys.
#:
#: The benchmark's lot runs the two sides down the length of a ten-metre
#: corridor in interleaved columns, which is a fine test fixture and looks
#: nothing like the place. Here the two groups FACE each other across the
#: width of the lot, a bare two metres apart.
STANDING = {
    # The Earps, in from Fremont at the mouth, in the order they walked.
    "virgil_earp":     (2.0, 3.6),
    "wyatt_earp":      (3.1, 3.7),
    "morgan_earp":     (4.2, 3.9),
    "doc_holliday":    (5.0, 4.5),
    # The Cowboys, backed against the Harwood house on the west side.
    "billy_clanton":   (1.6, 1.2),
    "frank_mclaury":   (2.9, 1.0),
    "tom_mclaury":     (4.2, 1.1),
    # Ike Clanton, unarmed, who ran at Wyatt and then ran for Fly's.
    "ike_clanton":     (3.4, 2.4),
    # Billy Claiborne, who left before the shooting and kept going.
    "billy_claiborne": (5.4, 1.0),
}


def the_lot_as_it_was():
    """The vacant lot beside Fly's, at the scale it was fought at.

    A FUNCTION AND NOT A CONSTANT, because `combatant_positions` is a
    mutable dict the fight writes into as people move. Calling this again
    after a fight gives the OPENING positions; reading them off the
    finished session gives the closing ones, which is a distinction a
    recorder needs and got wrong once.

    NOT `the_ok_corral.the_lot()`, which this used to borrow. That scene is
    a benchmark fixture: a ten-metre corridor with the two sides in
    interleaved columns down its length, buildings represented by a single
    wall face each, and no ground beyond the lot itself. It measures the
    engine well and it does not look like Tombstone -- PeterB, shown the
    replay: "doesnt much look like the tombstone layout". This one is
    built to be looked at.
    """
    from kirby_combat.scene.construct import Construct
    from kirby_combat.scene.scene import (
        Furnishing,
        AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
    )

    def wall(wid, name, a, b, *, h, cover, body, defv, part_of=None):
        return Wall(id=wid, name=name,
                    segment=(Position(*a, 0.0), Position(*b, 0.0)),
                    height_m=h, blocks_los=h >= 2.0, blocks_movement=True,
                    cover_level=cover, body=body, def_value=defv,
                    ed_value=6 if part_of else None, part_of=part_of,
                    climb_difficulty=-3 if part_of else 0)

    def building(oid, poly, *, h):
        """A real footprint, so it reads as a building and not a fin."""
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        return Construct(
            obj_id=oid, kind="wall",
            segment=(Position(xs[0], ys[0], 0.0), Position(xs[0], ys[-1], 0.0)),
            polygon_xy=list(poly), elevation_range_m=(0.0, h), height_m=h,
            blocks_los=True, blocks_movement=True, cover_level=4,
            def_value=8, body=30,
        )

    return Scene(
        id="fremont-lot", name="The vacant lot beside Fly's, Fremont Street",
        # TIGHT ON THE LOT, because the camera frames the BOUNDS
        # (`geometry.framingForBounds`). The first cut ran the street the
        # full width of Tombstone and the replay zoomed out until nine men
        # were a single smudge. The street still runs past the frame; the
        # bounds say where to look.
        bounds=SceneBounds(-3.0, -4.0, 0.0, 9.5, 7.5, 10.0),
        surfaces=[
            # TWO BIG TILES THAT DO NOT OVERLAP, which is the whole trick.
            # Coplanar surfaces at the same elevation z-fight, so the
            # ground stops exactly where the street starts rather than
            # running underneath it. Both extend well past the camera
            # bounds: the buildings sat on nothing before this, and a man
            # who ran out of the lot stood on black.
            # SMALL ON PURPOSE. These used to blanket the whole area, from
            # before there was a town: the recorder now lays Tombstone's
            # streets down first and the fight's own ground on top, so a
            # wide tile here paints over the town it is standing in. This
            # is the lot and the ground the men fight on, and no more.
            Surface(id="lot-ground", name="The vacant lot",
                    polygon_xy=[(-6.0, -8.0), (14.0, -8.0),
                                (14.0, 4.0), (-6.0, 4.0)],
                    elevation_m=0.0, surface_type="ground", cover_level=0),
        ],
        walls=[
            # The two faces that front the lot, eighteen feet apart.
            wall("harwood", "Harwood house (east wall)", (0.6, -3.0), (0.6, 4.0),
                 h=5.0, cover=4, body=3, defv=4, part_of="harwood-house"),
            wall("flys-lodgings", "C.S. Fly's boarding house (west wall)",
                 (5.6, -0.4), (5.6, 4.0), h=6.0, cover=4, body=3, defv=4,
                 part_of="flys-house"),
            wall("flys-studio", "C.S. Fly's photograph gallery",
                 (5.6, -3.0), (5.6, -0.6), h=4.5, cover=4, body=3, defv=4,
                 part_of="flys-house"),
            # The things to get behind are FURNISHINGS now, below --- a
            # wagon is a footprint and not a line. Their edges project
            # back into this list, so movement, line of sight, cover
            # moves, collapse and Area Of Effect all still see them.
        ],
        hazards=[], ambient=AmbientConditions(light_level=4),
        # WHAT WAS ACTUALLY IN THE LOT TO GET BEHIND, with real ground
        # under it. Authored as lines these had no width, so the renderer
        # invented 0.4 m for each and men stood inside them; a wagon is
        # four metres of bed and two of axle and everyone knows it.
        #
        # The wagon has moved NORTH of where its line sat. It had to: the
        # Earps come into the lot at y 3.6-3.9 and the line was at 4.1,
        # so any wagon of a real width had three of them standing in it.
        # A line could hide that; a footprint cannot.
        furnishings=[
            Furnishing(
                id="wagon", name="Photographer's wagon",
                polygon_xy=[(1.0, 4.6), (3.6, 4.6), (3.6, 6.0), (1.0, 6.0)],
                height_m=1.5, material="wooden wall", body=12, cover_level=2),
            Furnishing(
                id="barrels", name="Water barrels",
                polygon_xy=[(4.7, 1.9), (5.5, 1.9), (5.5, 3.0), (4.7, 3.0)],
                height_m=1.2, material="wooden wall", body=4, cover_level=2, portable=True),
            # Pulled west and south of where the line sat: the first
            # footprint drawn here had Billy Clanton standing inside the
            # crates at (1.6, 1.2), which the line it replaced could not
            # possibly have shown. That is the type doing its job on its
            # first outing.
            Furnishing(
                id="crates", name="Packing crates",
                polygon_xy=[(0.2, -0.4), (1.2, -0.4), (1.2, 0.6), (0.2, 0.6)],
                height_m=1.4, material="wooden wall", body=4, cover_level=2, portable=True),
            # SOMETHING A MAN CAN ACTUALLY LIFT. `pickup` and
            # `throw_object` had never fired in any benchmark. Three
            # breaks in one chain: a filter on a `kind` nothing created
            # (fixed earlier), no way for a SCENE to declare portability
            # (fixed now), and finally weight -- every man here is STR 10
            # and lifts 100 kg, while the barrels and crates are BODY 4 =
            # 200 kg at the engine's 50 kg/BODY. The engine was RIGHT to
            # refuse those: a full water barrel is not a one-man lift.
            # So the lot gets one small thing, which is scenery a
            # photographer's lot would have anyway.
            Furnishing(
                id="stool", name="Camp stool",
                # AGAINST THE GALLERY WALL, not in the lane. Placed at
                # (3.8-4.2, 2.9-3.3) it sat directly between the Cowboys
                # (y~1.0-2.4) and the Earps (y~3.6-4.5), and a Furnishing
                # projects its footprint into `scene.walls`. Measured: it
                # removed EVERY melee offer from the benchmark -- disarm,
                # grab, trip, block and strike all fell to zero, and
                # `disarm` had been chosen 7 times. One prop added to
                # reach two action kinds silently cost six others.
                # BEHIND the Earp line (y 3.6-4.5), not beside the lot: at
                # (0.4, 4.2) it was out of every man's reach and
                # `pickup` fell to zero again. Within a metre of
                # Virgil at (2.0, 3.6), and behind him.
                polygon_xy=[(1.2, 4.0), (1.6, 4.0), (1.6, 4.4), (1.2, 4.4)],
                height_m=0.5, material="wooden wall", body=1,
                # YOU STEP OVER A CAMP STOOL. `blocks_movement` defaults
                # True, which is right for a wagon and wrong for this.
                cover_level=0, blocks_movement=False, portable=True),
        ],
        constructs=[
            # The buildings themselves. The wall faces above front them;
            # these are the mass behind, and without them the lot is two
            # fins standing in the dark.
            building("harwood-house",
                     [(-3.0, -3.0), (0.6, -3.0), (0.6, 4.0), (-3.0, 4.0)], h=5.0),
            building("flys-house",
                     [(5.6, -3.0), (9.5, -3.0), (9.5, 4.0), (5.6, 4.0)], h=6.0),
        ],
        combatant_positions={
            cid: Position(x, y, 0.0) for cid, (x, y) in STANDING.items()
        },
    )


def the_scene():
    """The lot, freshly built, with only this cast standing in it."""
    return the_lot_as_it_was()


def the_fight(seed: int = DEMO_SEED, *, chooser=None):
    """Run it, and hand back the finished encounter.

    The LOT is imported from the benchmark rather than copied: terrain is
    geometry we authored and carries no licensed content, so the same
    Harwood House wall, Fly's Studio, wagon, barrels, trough and crates
    stand here. Only the men are different.
    """
    from dataclasses import replace

    from kirby_combat.encounter import Encounter
    from kirby_combat.loop import TacticChooser, run_encounter
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import RAW_HEROIC
    from kirby_dice import RandomRoller

    cast = the_cast()
    scene = the_scene()

    # 6E2 p.115's optional Bleeding rules, ON. The page frames them as a
    # choice -- "In situations where a character can get immediate
    # medical care, there's no need to use the Bleeding rules" -- and a
    # gunfight behind a saloon in 1881 is the case they were written for.
    # 6E2 p.109's bleeding to DEATH is core and applies either way.
    template = replace(RAW_HEROIC, use_bleeding_rules=True)

    roller = RandomRoller(seed=seed)
    # WHO DECIDES IS AN ARGUMENT. Doctrine is the default and the only
    # thing this repository can run on its own --- kirby-combat is Tier 1
    # pure and owns no network hop --- but the benchmark's whole job is to
    # show where the engine is thin, and "thin" means different repairs
    # depending on whether a MODEL also fails to reach a rule. See
    # `scripts/coverage.py`.
    chooser = chooser if chooser is not None else TacticChooser()
    session = CombatSession.create(
        id=f"shootout-{seed}", combatants=cast, scene=scene,
        template=template, dice_roller=roller).start()
    result = run_encounter(
        Encounter(id=f"shootout-{seed}", turn=1, segment=12,
                  sessions=[session], template=template),
        chooser, roller=roller, on_unresolvable="skip", max_turns=40)
    return chooser, result


if __name__ == "__main__":
    import sys as _sys

    seed = int(_sys.argv[1]) if len(_sys.argv) > 1 else DEMO_SEED
    chooser, result = the_fight(seed)
    session = result.encounter.sessions[0]
    print(f"seed {seed}: {result.phases} Phases, "
          f"{'winner ' + result.winner.name if result.winner else 'undecided'}")
    for c in session.combatants.values():
        state = c.state
        print(f"  {c.name:16} STUN {state.current_stun:4} BODY {state.current_body:3}"
              f"  {'DOWN' if state.current_stun <= 0 else 'up'}")
