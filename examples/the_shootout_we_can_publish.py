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
         dcv: int, stun: int, body: int, attacks=()):
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
        side=side, attacks=list(attacks),
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
        _man("doc_holliday", "Doc Holliday", law, dex=15, spd=3, ocv=7, dcv=5,
             stun=20, body=9, attacks=[shotgun(), revolver("Nickel revolver")]),
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


#: The seed the public demo records. Searched over 40 for the historical
#: result and several give it: exactly Billy Clanton and both McLaurys
#: down, Wyatt untouched, and Ike Clanton and Billy Claiborne --- who ran
#: --- alive. 21 is the longest of those at 22 Phases, which is the most
#: to watch. The one thing it does not reproduce is that Virgil, Morgan
#: and Doc were all wounded; here they come through clean.
DEMO_SEED = 21


def the_fight(seed: int = DEMO_SEED):
    """Run it, and hand back the finished encounter.

    The LOT is imported from the benchmark rather than copied: terrain is
    geometry we authored and carries no licensed content, so the same
    Harwood House wall, Fly's Studio, wagon, barrels, trough and crates
    stand here. Only the men are different.
    """
    from dataclasses import replace

    from the_ok_corral import the_lot
    from kirby_combat.encounter import Encounter
    from kirby_combat.loop import TacticChooser, run_encounter
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import RAW_HEROIC
    from kirby_dice import RandomRoller

    cast = the_cast()
    scene = the_lot()
    # Only the men who are actually here; `the_lot` places the benchmark's
    # nine under the same ids, so the positions carry across.
    here = {c.id for c in cast}
    scene = replace(scene, combatant_positions={
        k: v for k, v in scene.combatant_positions.items() if k in here})

    roller = RandomRoller(seed=seed)
    chooser = TacticChooser()
    session = CombatSession.create(
        id=f"shootout-{seed}", combatants=cast, scene=scene,
        template=RAW_HEROIC, dice_roller=roller).start()
    result = run_encounter(
        Encounter(id=f"shootout-{seed}", turn=1, segment=12,
                  sessions=[session], template=RAW_HEROIC),
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
