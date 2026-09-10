"""A second benchmark, built for the rules the O.K. Corral cannot reach.

WHY A SECOND SCENE AT ALL. The Corral is nine men inside four metres of
flat open ground, and `docs/gaps.md` records what that costs: the Range
Modifier never fires because every shot is inside 8m, hiding is never
worth a Phase because every enemy is already adjacent, and there is no
elevation at all. Three wired rules with no stage to stand on, and a
benchmark that cannot tell a correct refusal from a blind one.

Rewriting the Corral would have destroyed what it IS good at --- a
knife-range brawl where cover, hit locations and bleeding all bite. So
this is a different fight, and each of its features exists to make one
unreached rule reachable:

  * **FORTY-FIVE METRES between the sides at the start.** 6E2's table is
    -6 OCV in the 33-64m band, -4 from 17-32, -2 from 9-16, nothing
    inside 8. Closing is therefore a real decision with a number on it,
    and `move` --- offered 287 times at the Corral and taken never ---
    finally buys something a reader can price.
  * **A rifle that outranges a revolver.** Two weapons whose ranges
    differ by 4x makes "who can even reach" a question. At the Corral
    everyone held the same gun at the same distance.
  * **ROOFTOPS at 4.5m, and walls you can climb to reach them.** Height
    is what `reposition_vantage`, the fall rules and line-of-sight-versus-
    height were written for, and the Corral has none.
  * **ALLEY MOUTHS that block sight.** Cover at the Corral is
    chest-high --- you shoot over it. These are taller than a standing
    man, so breaking line of sight is possible, which is what makes
    hiding, and therefore 6E2 p.52's Surprised, worth a Phase.

AUTHORED, LIKE THE SHOOTOUT. Every character and weapon here is written
for this file. Nothing is loaded from the power library or any published
list, because those are paid Hero Games material and this repository
publishes what it can show.

    python examples/the_long_street.py
    python scripts/coverage.py --seeds 6 --scene street
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kirby_combat.models import AttackPower, DefenseItem
from kirby_combat.scene.scene import (
    AmbientConditions, Furnishing, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.side import Side
from kirby_combat.synthetic import synthetic_combatant

#: Chosen the way the Corral's is: for coverage, not for a story.
DEMO_SEED = 7

#: The street runs north along +y. The posse comes up it; the gang holds
#: the far end. 45m apart is deliberately the -6 OCV band.
POSSE_LINE_Y = 4.0
GANG_LINE_Y = 49.0

#: Rooftops. High enough to matter for falling (6E2's 2m-per-die) and to
#: see over everything on the street, low enough to climb in a Phase.
ROOF_M = 4.5


def rifle(name: str = "Winchester") -> AttackPower:
    """A lever-action carbine: reaches, and reloads slowly.

    2d6 Killing with no minus-one pip --- a shade heavier than the
    revolver below, and four times its range, which is the whole point of
    putting both in one fight.
    """
    return AttackPower(
        xmlid="RKA", name=name, damage_dice=2, half_die=False, plus_one=False,
        minus_one=False, damage_type="killing", defense_type="pd",
        range_m=200.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True,
        source_id=f"gun-{name.lower()}", charges=8, active_points=40,
    )


def revolver(name: str = "Revolver") -> AttackPower:
    """Short-ranged, and useless at the distance this fight opens at.

    50m of range against a 45m gap means a revolver CAN reach --- at -6
    OCV, into a man who is behind something. That is the decision the
    scene exists to pose.
    """
    return AttackPower(
        xmlid="RKA", name=name, damage_dice=2, half_die=False, plus_one=False,
        minus_one=True, damage_type="killing", defense_type="pd",
        range_m=50.0, uses_str=False, str_min=0, armor_piercing=0,
        penetrating=0, increased_stun_mult=0, is_ranged=True,
        source_id=f"gun-{name.lower().replace(' ', '-')}", charges=6,
        active_points=30,
    )


def _man(cid: str, name: str, side: Side, *, dex: int, spd: int, ocv: int,
         dcv: int, stun: int, body: int, attacks=(), skills=None):
    """One ordinary person. No characteristic is above what a 6E campaign
    would allow a competent human."""
    return synthetic_combatant(
        id=cid, name=name, ocv=ocv, dcv=dcv, omcv=3, dmcv=3, spd=spd,
        dex=dex, ego=10, int_=10, str_=10, con=13, pre=13, rec=4,
        pd=2, ed=2, rpd=0, red=0, md=0, power_defense=0, flash_defense=0,
        max_stun=stun, max_body=body, max_end=25,
        current_stun=stun, current_body=body, current_end=25,
        side=side, attacks=list(attacks), skills=skills,
        defenses=[DefenseItem(name="Coat", pd=1, rpd=1, is_resistant=True)],
        knockback_resistance=0,
    )


def the_sides() -> tuple[Side, Side]:
    posse = Side.named("Posse", objective=(
        "Close the street and take them. You are in the open and they are "
        "not — the distance is theirs until you shorten it."))
    gang = Side.named("Gang", objective=(
        "Hold the far end and the roof. Make them cross forty-five metres "
        "of open street to reach you."))
    return posse, gang


#: Where everybody starts. The posse is strung across the street's mouth;
#: the gang holds the top of it, one of them already on a roof.
#: WITHIN REACH OF SOMETHING, which the first layout was not and which
#: cost the scene most of its point. Two engine constants decide what a
#: fighter is even OFFERED:
#:
#:   * `CLIMB_FACE_REACH_M = 1.0` --- you must be within a METRE of a
#:     face to climb it. Ida started 2m off the stable front, so `climb`
#:     was offered zero times in six fights and both roofs were
#:     decoration.
#:   * cover must be inside a Half Move (6m). The nearest furnishing was
#:     8m from the posse, so `move_to_cover` and `hide` were offered zero
#:     times as well --- and doctrine never moves, so nothing ever came
#:     into reach later either.
#:
#: A scene has to put its affordances where the rules can see them.
STANDING: dict[str, tuple[float, float, float]] = {
    "marshal":   (5.0, POSSE_LINE_Y, 0.0),
    "deputy":    (8.5, POSSE_LINE_Y - 1.0, 0.0),
    # Hard against the livery front, so the climb to the roof is on her
    # menu from the first Phase.
    "tracker":   (0.8, POSSE_LINE_Y - 1.0, 0.0),
    "boss":      (6.0, GANG_LINE_Y, 0.0),
    "rifleman":  (1.5, GANG_LINE_Y + 3.0, ROOF_M),
    # Against the saloon front at the far end, for the same reason.
    "kid":       (10.2, GANG_LINE_Y - 1.0, 0.0),
}


def the_cast() -> list:
    """Six people. Invented, like their guns."""
    posse, gang = the_sides()
    return [
        _man("marshal", "Marshal Vane", posse, dex=14, spd=3, ocv=7, dcv=5,
             stun=26, body=11, attacks=[rifle("Marshal's carbine")],
             skills={"PARAMEDICS": 11}),
        _man("deputy", "Deputy Sark", posse, dex=12, spd=3, ocv=6, dcv=4,
             stun=24, body=10, attacks=[revolver("Deputy's revolver")]),
        _man("tracker", "Ida Crowe", posse, dex=15, spd=3, ocv=7, dcv=5,
             stun=22, body=10, attacks=[rifle("Crowe's rifle")],
             skills={"STEALTH": 12, "CLIMBING": 12}),
        _man("boss", "Rell Hoyt", gang, dex=13, spd=3, ocv=6, dcv=4,
             stun=26, body=11, attacks=[revolver("Hoyt's revolver")]),
        _man("rifleman", "Beck", gang, dex=14, spd=3, ocv=7, dcv=4,
             stun=22, body=10, attacks=[rifle("Beck's rifle")],
             skills={"STEALTH": 11}),
        _man("kid", "The Kid", gang, dex=12, spd=2, ocv=5, dcv=4,
             stun=20, body=10, attacks=[revolver("The Kid's revolver")]),
    ]


def _facade(wid: str, name: str, a: tuple[float, float],
            b: tuple[float, float], *, part_of: str) -> Wall:
    """A building front: tall enough to block sight, and climbable.

    `climb_difficulty=0` is the engine's "ordinary handholds, no Climbing
    roll needed" --- a false front with a porch post. Sheer would be None
    and would put the roofs out of reach, which would waste them.
    """
    return Wall(
        id=wid, name=name,
        segment=(Position(a[0], a[1], 0.0), Position(b[0], b[1], 0.0)),
        height_m=ROOF_M, blocks_los=True, blocks_movement=True,
        cover_level=4, body=4, def_value=4, ed_value=6,
        part_of=part_of, climb_difficulty=0, walkable_width_m=0.0,
    )


def the_street() -> Scene:
    """Fremont Street at its long end: two rows of fronts, and the gap."""
    return Scene(
        id="long-street", name="The long end of the street",
        bounds=SceneBounds(-14.0, -6.0, 0.0, 26.0, 62.0, 20.0),
        surfaces=[
            Surface(id="street", name="Street",
                    polygon_xy=[(-14, -6), (26, -6), (26, 62), (-14, 62)],
                    elevation_m=0.0, surface_type="road", cover_level=0),
            # THE ROOFS. `is_supporting` is what lets anybody stand on
            # one; without it a climber falls through.
            Surface(id="west-roof", name="Roof of the feed store",
                    polygon_xy=[(-13, 44), (0, 44), (0, 58), (-13, 58)],
                    elevation_m=ROOF_M, surface_type="rooftop",
                    cover_level=0, is_supporting=True),
            Surface(id="east-roof", name="Roof of the assay office",
                    polygon_xy=[(11, 14), (25, 14), (25, 30), (11, 30)],
                    elevation_m=ROOF_M, surface_type="rooftop",
                    cover_level=0, is_supporting=True),
        ],
        walls=[
            # West side, north to south. The gap between the last two is
            # an alley mouth: somewhere to break line of sight.
            _facade("feed-store", "Feed store front", (0.0, 44.0), (0.0, 58.0),
                    part_of="feed-store-bldg"),
            _facade("west-hotel", "Hotel front", (0.0, 22.0), (0.0, 38.0),
                    part_of="west-hotel-bldg"),
            _facade("west-stable", "Livery stable front", (0.0, 2.0), (0.0, 16.0),
                    part_of="west-stable-bldg"),
            # East side.
            _facade("assay", "Assay office front", (11.0, 14.0), (11.0, 30.0),
                    part_of="assay-bldg"),
            _facade("east-saloon", "Saloon front", (11.0, 34.0), (11.0, 52.0),
                    part_of="east-saloon-bldg"),
        ],
        hazards=[], ambient=AmbientConditions(light_level=4),
        furnishings=[
            # Cover strung down the street, so closing forty-five metres
            # is a series of decisions rather than one long run.
            # Inside a Half Move of the posse line, so taking cover is a
            # choice on the first Phase rather than a reward for a walk
            # nobody takes.
            Furnishing(id="trough", name="Water trough",
                       polygon_xy=[(2.6, 7.4), (4.6, 7.4),
                                   (4.6, 8.4), (2.6, 8.4)],
                       height_m=1.0, material="wooden wall", body=6),
            Furnishing(id="freight", name="Freight wagon",
                       polygon_xy=[(5.5, 26.0), (9.5, 26.0),
                                   (9.5, 28.0), (5.5, 28.0)],
                       height_m=1.5, material="wooden wall", body=12),
            # TALLER THAN A STANDING MAN, which is the point: this is the
            # one thing on the board you can genuinely get out of sight
            # behind, and therefore the one that makes hiding pay.
            Furnishing(id="crates", name="Stack of freight crates",
                       polygon_xy=[(1.0, 33.0), (3.4, 33.0),
                                   (3.4, 35.4), (1.0, 35.4)],
                       height_m=2.4, material="wooden wall", body=6),
            Furnishing(id="barrels", name="Rain barrels",
                       polygon_xy=[(8.0, 45.0), (9.6, 45.0),
                                   (9.6, 46.6), (8.0, 46.6)],
                       height_m=1.2, material="wooden wall", body=4),
            # Tall, and inside a Half Move of the gang line: the far end
            # gets something to break sight behind too, or "hide" is a
            # choice only one side is ever offered.
            Furnishing(id="stack", name="Stacked hides",
                       polygon_xy=[(3.0, 45.0), (5.2, 45.0),
                                   (5.2, 47.2), (3.0, 47.2)],
                       height_m=2.4, material="wooden wall", body=6),
        ],
        combatant_positions={
            cid: Position(x, y, z) for cid, (x, y, z) in STANDING.items()
        },
    )


def the_fight(seed: int = DEMO_SEED, *, chooser=None):
    """Run it, and hand back the finished encounter."""
    from dataclasses import replace

    from kirby_combat.encounter import Encounter
    from kirby_combat.loop import TacticChooser, run_encounter
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import RAW_HEROIC
    from kirby_dice import RandomRoller

    template = replace(RAW_HEROIC, use_bleeding_rules=True)
    roller = RandomRoller(seed=seed)
    chooser = chooser if chooser is not None else TacticChooser()
    session = CombatSession.create(
        id=f"street-{seed}", combatants=the_cast(), scene=the_street(),
        template=template, dice_roller=roller).start()
    return chooser, run_encounter(
        Encounter(id=f"street-{seed}", turn=1, segment=12,
                  sessions=[session], template=template),
        chooser, roller=roller, on_unresolvable="skip", max_turns=40)


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else DEMO_SEED
    chooser, result = the_fight(seed)
    session = result.encounter.sessions[0]
    print(f"seed {seed}: {result.phases} Phases, "
          f"{'winner ' + result.winner.name if result.winner else 'undecided'}")
    for c in session.combatants.values():
        s = c.state
        print(f"  {c.name:16} STUN {s.current_stun:4} BODY {s.current_body:3}"
              f"  {'DOWN' if s.current_stun <= 0 else 'up'}")
