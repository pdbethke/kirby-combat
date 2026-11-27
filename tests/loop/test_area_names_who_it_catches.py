"""An Area offer says who it would catch, and doctrine does not fire one
through its own side.

Found at the O.K. Corral (2026-11-27): Doc Holliday's shotgun cone caught
all eight men in the lot, Wyatt and Virgil Earp with them, and doctrine
fired it on his first Phase. Nothing on the offer said who stood in it.
Peter, 2026-11-27: the offer names who is in the area, and doctrine refuses
an area that catches an ally. (A model seat still sees the offer, with the
names on it, and may choose it.)
"""
from __future__ import annotations

from shaped import Dice, armed, encounter_on, scene_with, shaped_blast
from kirby_combat.loop.chooser import TacticChooser
from kirby_combat.loop.run import _situation_for
from kirby_combat.power_modifiers import AreaShape, AreaSpec, AreaTargeting
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")
#: b and c are the enemy; e is a's own man, standing beside b.
POSITIONS = {"a": (0, 0, 0), "b": (8, 0, 0), "c": (11, 0, 0), "e": (9, 1, 0)}


def _session(positions=POSITIONS):
    spec = AreaSpec(shape=AreaShape.RADIUS, size_m=4.0, targeting=AreaTargeting.STANDARD,
                    explosion=False, personal_immunity=False, width_m=2.0,
                    height_m=2.0, thin_cone=False, unbuilt=())
    storm = shaped_blast("a-storm", 4, area=spec)
    people = [armed("a", storm, side=VILLAINS, dex=30),
              armed("b", None, side=HEROES), armed("c", None, side=HEROES),
              armed("e", None, side=VILLAINS)]
    people = [p for p in people if p.id in positions]
    return encounter_on(scene_with(positions), *people).sessions[0]


def _area_offers(situation, target):
    return [o for o in situation.menu if o.kind == "attack" and o.target_id == target
            and getattr(o._attack_view, "area", None) is not None]


def test_the_offer_names_his_own_man_in_the_area():
    offer = _area_offers(_situation_for(_session(), "a"), "b")[0]
    assert set(offer._area_catches) == {"b", "c", "e"}
    assert "YOUR OWN SIDE: e" in offer.summary, offer.summary


def test_doctrine_will_not_fire_it_through_his_own_man():
    situation = _situation_for(_session(), "a")
    chosen = TacticChooser().choose(situation)
    caught = {o.action_id for o in situation.menu if getattr(o, "_area_allies", ())}
    assert caught, "the area offer should be marked as catching e"
    assert chosen not in caught


def test_with_nobody_of_his_in_it_doctrine_may_fire():
    clear = {k: v for k, v in POSITIONS.items() if k != "e"}
    situation = _situation_for(_session(clear), "a")
    assert not any(getattr(o, "_area_allies", ()) for o in situation.menu)
