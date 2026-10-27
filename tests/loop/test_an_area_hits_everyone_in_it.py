"""An Area Of Effect attack hits everyone in the area, from one roll.

6E1 p.321: "a character targets the center of the area on a target point
(which has DCV 3). Then he makes an Attack Roll ... An Area Of Effect power
affects all the characters in the area ... the character rolls damage once
and each victim takes that damage". The engine read none of it: an AOE Blast
hit the one man the menu named, at his own DCV, like any other Blast. The
deleted api driver hit every living enemy on the map wherever he stood.

The scene: the attacker at the origin, the named target 8m out (no Range
Modifier, outside 2m so the target point is DCV 3), a second hero 3m past
him, the attacker's own ally beside him, and a third hero 12m off.
"""
from __future__ import annotations

from shaped import (                                    # tests/loop/shaped.py
    TEMPLATE, Dice, Picks, armed, encounter_on, payloads, scene_with,
    shaped_blast,
)
from kirby_combat.attack_shapes import offer_is_buildable
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.power_modifiers import AreaShape, AreaSpec, AreaTargeting
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")
POSITIONS = {"a": (0, 0, 0), "b": (8, 0, 0), "c": (11, 0, 0),
             "e": (9, 1, 0), "d": (20, 0, 0)}


def area(size=7.0, shape=AreaShape.RADIUS, targeting=AreaTargeting.STANDARD,
         explosion=False, personal_immunity=False, unbuilt=()):
    return AreaSpec(shape=shape, size_m=size, targeting=targeting,
                    explosion=explosion, personal_immunity=personal_immunity,
                    width_m=2.0, height_m=2.0, thin_cone=False,
                    unbuilt=tuple(unbuilt))


def _fight(spec, *, positions=POSITIONS, dcv=5, ranged=True):
    power = shaped_blast("a-storm", 4, area=spec)
    if not ranged:
        from dataclasses import replace
        power = replace(power, range_m=0, is_ranged=False)
    people = [armed("a", power, side=VILLAINS, dex=30),
              armed("b", None, side=HEROES, dcv=dcv),
              armed("c", None, side=HEROES, dcv=dcv),
              armed("e", None, side=VILLAINS),
              armed("d", None, side=HEROES)]
    people = [p for p in people if p.id in positions]
    return encounter_on(scene_with(positions), *people), power


def _offer(power, target="b"):
    return LegalAction(action_id=f"attack:{target}:a-storm", kind="attack",
                       target_id=target, power_xmlid=power.xmlid,
                       power_name=power.name, summary="", _attack_view=power)


def _stun(session, who):
    return session.combatants[who].state.current_stun


def test_everyone_in_the_area_takes_the_one_damage_roll_through_run_phase():
    """Seam: the menu offers the Area power, `run_phase` resolves it, and
    b, c and the attacker's own ally e all take 4d6 of 3s = 12 STUN less ED 4.
    d, 12m from the target point, is outside the 7m Radius (and so is the
    attacker himself, 8m from it --- at 8m he would be in his own blast)."""
    enc, _ = _fight(area())
    chooser = Picks(lambda a, _s: a.kind == "attack" and a.target_id == "b")
    result = run_phase(enc, chooser, roller=Dice(face=3),
                       on_unresolvable="raise")
    s = result.session
    assert result.actor_id == "a" and result.kind == "attack"
    for who in ("b", "c", "e"):
        assert _stun(s, who) == 40 - (12 - 4), who
    assert _stun(s, "d") == 40
    use = payloads(s, area_use=True)
    assert len(use) == 1
    assert sorted(use[0]["victims"]) == ["b", "c", "e"]


def test_the_roll_is_against_the_target_point_not_the_man():
    """DCV 3, whatever his own DCV. Against DCV 12 a roll of 13 (OCV 9) needs
    11 + 9 - 12 = 8 or less and misses; against the point (DCV 3) it hits."""
    enc, power = _fight(area(), dcv=12)
    s = enc.sessions[0]
    dice = Dice(face=3, queue=[[5, 4, 4]])
    resolved = resolve_chosen(s, s.combatants["a"], _offer(power),
                              template=TEMPLATE, roller=dice)
    use = payloads(resolved.session, area_use=True)[0]
    assert use["target_dcv"] == 3
    assert use["hit"] is True
    assert _stun(resolved.session, "b") < 40


def test_one_use_spends_one_charge():
    """`charges.spent_charges` counts rows carrying the power's id. The use
    carries it; the victims' rows do not --- three men hit is one shot."""
    from kirby_combat.charges import spent_charges

    enc, power = _fight(area())
    s = enc.sessions[0]
    resolved = resolve_chosen(s, s.combatants["a"], _offer(power),
                              template=TEMPLATE, roller=Dice(face=3))
    assert spent_charges(resolved.session, "a") == {"a-storm": 1}


def test_a_miss_lands_somewhere_else_and_may_still_catch_him():
    """6E2 p.42: 2m per point missed, at most half the distance, d6 for the
    direction. 3d6 = 18 always misses (6E2 p.37), here by 1, so the point
    moves 2m; the d6 = 1 sends it long, past him (the labelled ruling), to
    (10, 0). b (2m), c (1m) and e (1.4m) are all still in the 7m Radius."""
    enc, power = _fight(area())
    s = enc.sessions[0]
    dice = Dice(face=3, queue=[[6, 6, 6], [1, 1, 1, 1], [3, 3, 3], [3], [1]])
    resolved = resolve_chosen(s, s.combatants["a"], _offer(power),
                              template=TEMPLATE, roller=dice)
    use = payloads(resolved.session, area_use=True)[0]
    assert use["hit"] is False
    assert use["deviated_m"] == 2.0
    assert [round(v, 6) for v in use["target_point"]] == [10.0, 0.0, 0.0]
    assert sorted(use["victims"]) == ["b", "c", "e"]


def test_the_miss_direction_can_take_it_off_him():
    """Same miss, d6 = 4: back toward the attacker, to (6, 0) --- which puts
    the attacker, 6m away, inside his own 7m blast and leaves d (14m) out."""
    enc, power = _fight(area())
    s = enc.sessions[0]
    dice = Dice(face=3, queue=[[6, 6, 6], [1, 1, 1, 1], [3, 3, 3], [3], [4]])
    resolved = resolve_chosen(s, s.combatants["a"], _offer(power),
                              template=TEMPLATE, roller=dice)
    use = payloads(resolved.session, area_use=True)[0]
    assert [round(v, 6) for v in use["target_point"]] == [6.0, 0.0, 0.0]
    assert "a" in use["victims"] and "d" not in use["victims"]


def test_an_explosion_loses_the_biggest_die_per_two_metres():
    """6E1 p.325: full effect to 2m, then one DC per 2m, "the largest die
    rolled first". c is 3m from the point: loses the 6, so 5+4+3 = 12 STUN
    less ED 4 = 8; b at the point takes all 18, less 4 = 14."""
    enc, power = _fight(area(explosion=True))
    s = enc.sessions[0]
    dice = Dice(face=3, queue=[[3, 3, 3], [6, 5, 4, 3]])
    resolved = resolve_chosen(s, s.combatants["a"], _offer(power),
                              template=TEMPLATE, roller=dice)
    assert _stun(resolved.session, "b") == 40 - 14
    assert _stun(resolved.session, "c") == 40 - 8


def test_a_no_range_area_is_centred_on_the_attacker_and_hits_him_too():
    """6E1 p.321: "the center of the Area Of Effect is the character himself
    ... he takes full effect unless he's somehow protected (such as ...
    Personal Immunity)"."""
    near = {"a": (0, 0, 0), "b": (1, 0, 0), "d": (20, 0, 0)}
    enc, power = _fight(area(size=4.0), positions=near, ranged=False)
    s = enc.sessions[0]
    hit = resolve_chosen(s, s.combatants["a"], _offer(power),
                         template=TEMPLATE, roller=Dice(face=3))
    assert _stun(hit.session, "a") < 40 and _stun(hit.session, "b") < 40
    assert _stun(hit.session, "d") == 40

    enc, power = _fight(area(size=4.0, personal_immunity=True),
                        positions=near, ranged=False)
    s = enc.sessions[0]
    immune = resolve_chosen(s, s.combatants["a"], _offer(power),
                            template=TEMPLATE, roller=Dice(face=3))
    assert _stun(immune.session, "a") == 40


def test_selective_spares_his_friends():
    """6E1 p.326: Selective "can ignore 'friendlies' in the area"."""
    enc, power = _fight(area(targeting=AreaTargeting.SELECTIVE))
    s = enc.sessions[0]
    resolved = resolve_chosen(s, s.combatants["a"], _offer(power),
                              template=TEMPLATE, roller=Dice(face=3))
    assert _stun(resolved.session, "e") == 40
    assert _stun(resolved.session, "b") < 40


def test_a_cone_opens_away_from_the_attacker():
    """6E1 p.322: a Cone's point is "at the very end of the angle that points
    toward the character". A man behind the attacker is not in it."""
    positions = {"a": (0, 0, 0), "b": (8, 0, 0), "c": (14, 2, 0),
                 "d": (-6, 0, 0)}
    enc, power = _fight(area(size=10.0, shape=AreaShape.CONE), positions=positions)
    s = enc.sessions[0]
    resolved = resolve_chosen(s, s.combatants["a"], _offer(power),
                              template=TEMPLATE, roller=Dice(face=3))
    use = payloads(resolved.session, area_use=True)[0]
    assert sorted(use["victims"]) == ["b", "c"]


def test_an_area_the_engine_cannot_resolve_is_not_offered():
    """An Area part `power_modifiers` cannot build (here Any Area, 6E1
    p.323: the attacker arranges its 2m Areas "as desired" each use, which
    no offer says) keeps the power off the menu. (This used to be Surface,
    which `standing_areas.py` builds now.)"""
    spec = area(shape=AreaShape.ANY, unbuilt=("Area Of Effect (Any Area)",))
    enc, power = _fight(spec)
    chooser = Picks(lambda a, _s: False)
    run_phase(enc, chooser, roller=Dice(face=3), on_unresolvable="raise")
    offered = [a for a in chooser.menus[0]
               if getattr(a, "_attack_view", None) is not None
               and a._attack_view.source_id == "a-storm"]
    assert offered == []


def test_an_area_power_can_be_a_rapid_fire_but_not_a_spread():
    """6E2 p.76 lists among the Multiple Attacks a character may make "use a
    Blast and an RKA, Area Of Effect against a single target or multiple
    targets" --- so a burst of Area shots is built: each shot goes to the
    attack door, which lays its own Area. Batch C refused it, reading 6E1
    p.321's price for Autofire on an Area as a ban; the page bans Spread
    instead: "Characters cannot Spread Area Of Effect attacks"."""
    enc, power = _fight(area())
    burst = LegalAction(action_id="rapid_fire:b:a-storm:2", kind="rapid_fire",
                        target_id="b", power_xmlid=power.xmlid,
                        power_name=power.name, summary="", _attack_view=power)
    spread = LegalAction(action_id="spread:b:a-storm", kind="spread",
                         target_id="b", power_xmlid=power.xmlid,
                         power_name=power.name, summary="", _attack_view=power)
    s = enc.sessions[0]
    assert offer_is_buildable(s, "a", burst) is True
    assert offer_is_buildable(s, "a", spread) is False
    resolved = resolve_chosen(s, s.combatants["a"], burst,
                              template=TEMPLATE, roller=Dice(face=3))
    uses = payloads(resolved.session, area_use=True)
    assert len(uses) == 2
    assert all(u["target_dcv"] == 3 for u in uses)


def test_a_real_build_carries_its_area():
    """Ravel's String Storm is bought with Area Of Effect (8m Radius); the
    attack view the engine fights with now says so."""
    from corpus import require_authored
    from kirby_combat.hero_view import HeroCombatant

    ravel = HeroCombatant.from_build(require_authored("Ravel"), id="ravel")
    storms = [a for a in ravel.attacks
              if getattr(a, "area", None) is not None]
    assert storms, "Ravel's Area powers reached combat without their Area"
    radius = [a.area for a in storms if a.area.shape is AreaShape.RADIUS]
    assert any(r.size_m == 8.0 for r in radius)
