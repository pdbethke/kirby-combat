"""An Area's victims each roll their own Hit Location.

6E1 p.321: an Area Of Effect attack's damage is rolled once and "each victim
takes that damage". Where it lands on each man is another matter: Western
Hero p.159 gives the GM two choices for an Area with Hit Locations --- roll
Hit Locations as normal, or ignore them --- and RULING (Peter, 2026-11-27):
roll them as normal, for each victim. Before this every victim took the one
location rolled for the attack: one shotgun blast hit eight men in the
Stomach.
"""
from __future__ import annotations

from dataclasses import replace

from shaped import TEMPLATE, Picks, armed, encounter_on, payloads, scene_with, shaped_blast
from kirby_combat.loop import run_phase
from kirby_combat.power_modifiers import AreaShape, AreaSpec, AreaTargeting
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")
POSITIONS = {"a": (0, 0, 0), "b": (8, 0, 0), "c": (11, 0, 0), "e": (9, 1, 0)}


class _Turning:
    """The first 3d6 is a 3 (the Area's one Attack Roll hits, 6E2 p.37).
    After it every die of a roll shows the same face, and the face moves on
    one each roll, so no two consecutive location rolls agree."""

    def __init__(self):
        self.face = 0
        self.rolled_to_hit = False

    def roll_dice(self, count, sides):
        if count == 3 and not self.rolled_to_hit:
            self.rolled_to_hit = True
            return [1, 1, 1]
        self.face = self.face % 6 + 1
        return [self.face] * count


def test_each_victim_rolls_his_own_location():
    rules = replace(TEMPLATE, use_hit_locations=True)
    spec = AreaSpec(shape=AreaShape.RADIUS, size_m=7.0, targeting=AreaTargeting.STANDARD,
                    explosion=False, personal_immunity=False, width_m=2.0,
                    height_m=2.0, thin_cone=False, unbuilt=())
    power = shaped_blast("a-storm", 4, area=spec)
    people = [armed("a", power, side=VILLAINS, dex=30),
              armed("b", None, side=HEROES, dcv=0), armed("c", None, side=HEROES, dcv=0),
              armed("e", None, side=VILLAINS)]
    enc = encounter_on(scene_with(POSITIONS), *people, template=rules)
    result = run_phase(enc, Picks(lambda a, _s: a.kind == "attack" and a.target_id == "b"),
                       roller=_Turning(), on_unresolvable="raise")
    rows = [p for p in payloads(result.session)
            if "hit" in p and not p.get("area_use") and p.get("target_id") in ("b", "c", "e")]
    hit = [p for p in rows if p["hit"]]
    assert len(hit) >= 2, rows
    assert len({p["location"] for p in hit}) > 1, [p["location"] for p in hit]
