"""Dive for Cover: the Abort everyone inside an Area Of Effect is offered.

6E2 p.87: he moves up to half his maximum movement, with the mode he is
using, and makes a DEX Roll at -1 per 2m moved. Success puts him at the
point, prone, at half DCV until his next Phase. Failure leaves him "in the
air" where he started: his DCV does not change, Knockback against him is
rolled with 1d6 less, and he lands prone at his next Phase. It is an Abort
(6E2 p.23, p.25), so it costs his next Phase.

The old code got the failure wrong (half DCV and +2 OCV to the attacker,
which the book does not say), and only the named man was ever asked.

The scene: the attacker at the origin, the named man 10m out with a second
hero 2m past him, and a third far off. The area is a 4m Radius, so a man on
Running 12 (half: 6m) can get out of it.
"""
from __future__ import annotations

from types import SimpleNamespace

from shaped import (                                    # tests/loop/shaped.py
    TEMPLATE, Dice, Picks, armed, encounter_on, scene_with, shaped_blast,
)
from kirby_combat.actions.area_attack import aimed_area
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop import run_phase
from kirby_combat.loop.reactions import (
    Reaction, area_defenders, dive_destination, reaction_menu,
)
from kirby_combat.power_modifiers import AreaShape, AreaSpec, AreaTargeting
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


def area(size: float) -> AreaSpec:
    return AreaSpec(shape=AreaShape.RADIUS, size_m=size,
                    targeting=AreaTargeting.STANDARD, explosion=False,
                    personal_immunity=False, width_m=2.0, height_m=2.0,
                    thin_cone=False, unbuilt=())


def _fight(size: float, positions: dict, *, extra=()):
    power = shaped_blast("a-storm", 4, area=area(size))
    people = [armed("a", power, side=VILLAINS, dex=30)]
    # Distinct DEX, so no tie for the acting order is rolled before the dive.
    heroes = [who for who in positions if who != "a"]
    people += [armed(who, None, side=HEROES, dex=20 - i)
               for i, who in enumerate(heroes)]
    return encounter_on(scene_with(positions), *people), power


def _offer(power, target="b"):
    return LegalAction(action_id=f"attack:{target}:a-storm", kind="attack",
                       target_id=target, power_xmlid=power.xmlid,
                       power_name=power.name, summary="", _attack_view=power)


SMALL = {"a": (0, 0, 0), "b": (10, 0, 0), "c": (12, 0, 0), "d": (30, 0, 0)}


def _dist(p, q) -> float:
    return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2) ** 0.5


def _xyz(pos) -> tuple[float, float, float]:
    return (pos.x, pos.y, pos.z)


def _b_dives(action, situation) -> bool:
    if action.kind == "attack" and action.target_id == "b":
        return True
    return action.kind == Reaction.DIVE_FOR_COVER.value and situation.actor.id == "b"


# ---------------------------------------------------------------------------
# Who is asked, and where he would go
# ---------------------------------------------------------------------------

def test_everyone_in_the_area_is_asked():
    """An 18m Radius on b holds b, c and e; d, 20m off, is outside it. The
    named man is first."""
    enc, power = _fight(18.0, {"a": (0, 0, 0), "b": (40, 0, 0),
                               "c": (45, 0, 0), "e": (40, 10, 0),
                               "d": (60, 0, 0)})
    s = enc.sessions[0]
    got = area_defenders(s, s.combatants["a"], _offer(power))
    assert got[0] == "b"
    assert sorted(got) == ["b", "c", "e"]


def test_dive_destination_is_outside_and_within_half_move():
    enc, power = _fight(4.0, SMALL)
    s = enc.sessions[0]
    aimed = aimed_area(s, "a", "b", power)
    dest = dive_destination(s, "b", aimed)
    assert dest is not None
    start = (10.0, 0.0, 0.0)
    # Outside the 4m Radius on b's spot, and no further than he has to go
    # (the search steps a quarter metre at a time).
    assert 4.0 < _dist(_xyz(dest), start) <= 4.25 + 1e-9
    # Half of Running 12 (6E2 p.87).
    assert _dist(_xyz(dest), start) <= 6.0
    assert not aimed.holds(_xyz(dest))


def test_no_reachable_point_means_no_dive_offer():
    """An 18m Radius: half of Running 12 is 6m, and nowhere 6m away is out
    of it. Only `no_abort` is offered."""
    enc, power = _fight(18.0, SMALL)
    s = enc.sessions[0]
    assert dive_destination(s, "b", aimed_area(s, "a", "b", power)) is None
    menu = reaction_menu(s, s.combatants["a"], _offer(power), "b")
    assert [m.kind for m in menu] == [Reaction.NONE.value]


def test_a_dive_is_offered_with_its_destination_when_there_is_one():
    enc, power = _fight(4.0, SMALL)
    s = enc.sessions[0]
    menu = reaction_menu(s, s.combatants["a"], _offer(power), "b")
    assert [m.kind for m in menu] == [Reaction.NONE.value,
                                     Reaction.DIVE_FOR_COVER.value]
    dive = menu[1]
    assert dive.mode == "running"
    assert dive.reposition_dest is not None
    assert "6E2 p.87" in dive.summary


def test_flyer_dives_by_flight():
    """In the air, he dives with the mode he is using: Flight (RULING on
    6E2 p.87's "with the mode of movement used"). An 8m Radius: half of his
    Running 12 would not get him out; half of Flight 20 does."""
    enc, power = _fight(8.0, {"a": (0, 0, 0), "b": (10, 0, 5), "d": (30, 0, 0)})
    s = enc.sessions[0]
    caps = [SimpleNamespace(mode="running", combat_m=12.0),
            SimpleNamespace(mode="flight", combat_m=20.0)]
    object.__setattr__(s.combatants["b"], "movement_view", lambda: caps)
    menu = reaction_menu(s, s.combatants["a"], _offer(power), "b")
    dive = [m for m in menu if m.kind == Reaction.DIVE_FOR_COVER.value]
    assert len(dive) == 1
    assert dive[0].mode == "flight"
    dest = dive[0].reposition_dest
    assert dest[2] == 5
    assert 8.0 < _dist(dest, (10, 0, 5)) <= 10.0


def test_no_map_means_no_dive():
    enc, power = _fight(4.0, SMALL)
    from dataclasses import replace

    s = replace(enc.sessions[0], scene=None)
    menu = reaction_menu(s, s.combatants["a"], _offer(power), "b")
    assert [m.kind for m in menu] == [Reaction.NONE.value]


# ---------------------------------------------------------------------------
# The dive, through run_phase
# ---------------------------------------------------------------------------

def _dived(session, who):
    return [e for e in session.event_log
            if e.kind == "DivedForCover" and e.combatant_id == who]


def test_successful_dive_moves_him_prone_out_of_the_area():
    """Dice of 2s: the DEX Roll (6) makes it. He is out of the area when it
    goes off and takes nothing; c, who stayed, takes the blast (4d6 of 2s,
    8 STUN less ED 4), so the area went where it was aimed and did not
    follow him."""
    from kirby_combat.cv_modifiers import _ground_cv_modifiers
    from kirby_combat.statuses import PRONE, statuses_for

    enc, _ = _fight(4.0, SMALL)
    result = run_phase(enc, Picks(_b_dives), roller=Dice(face=2),
                       on_unresolvable="raise")
    s = result.session
    assert result.actor_id == "a" and result.kind == "attack"
    [dive] = _dived(s, "b")
    assert dive.success and dive.against_id == "a"
    assert dive.roll == 6 and dive.target == 13 - 3   # 4.25m: -3 (6E2 p.87)
    moves = [e for e in s.event_log
             if e.kind == "MovementResolved" and e.combatant_id == "b"]
    assert moves and moves[-1].to_pos["x"] == dive.destination["x"]
    here = s.scene.combatant_positions["b"]
    assert (here.x, here.y) == (dive.destination["x"], dive.destination["y"])
    assert s.combatants["b"].state.current_stun == 40
    assert s.combatants["c"].state.current_stun == 40 - (8 - 4)
    assert PRONE in statuses_for(s, "b")
    assert _ground_cv_modifiers(s, "b", "a", "ranged")["dcv_factor"] == 0.5


def test_failed_dive_leaves_him_in_the_air_dcv_unchanged():
    """Dice of 6s on the DEX Roll: he fails. He is still where he was, so the
    area catches him; his DCV is unchanged and the attacker gets no bonus;
    Knockback against him is rolled with 1d6 less; and he lands prone at his
    next Phase. 6E2 p.87, replacing the old half DCV and +2 OCV."""
    from kirby_combat.cv_modifiers import _ground_cv_modifiers, cv_modifiers_for
    from kirby_combat.impact import knockback_dice_for
    from kirby_combat.statuses import IN_THE_AIR, PRONE, statuses_for

    # b is the slowest hero (DEX 18, after c and d), so his next Phase is
    # not the very next one and he is seen in the air between the two.
    enc, power = _fight(4.0, {"a": (0, 0, 0), "c": (12, 0, 0),
                              "d": (30, 0, 0), "b": (10, 0, 0)})
    attack = SimpleNamespace(power=power, target=SimpleNamespace(id="b"))
    before = knockback_dice_for(enc.sessions[0], attack, TEMPLATE,
                                rolled_with_punch=False)
    # The Segment's acting order rolls one 3d6 tie-break per man first
    # (`resolve_acting_order`); the fifth roll is the dive's DEX Roll.
    ties = [[3, 3, 3]] * 4
    result = run_phase(enc, Picks(_b_dives),
                       roller=Dice(face=3, queue=ties + [[6, 6, 6]]),
                       on_unresolvable="raise")
    s = result.session
    [dive] = _dived(s, "b")
    assert not dive.success and dive.roll == 18 and dive.destination is None
    # He did not move: the only move is the blast knocking him back, from
    # where he started.
    moves = [e for e in s.event_log
             if e.kind == "MovementResolved" and e.combatant_id == "b"]
    assert [e.move_type for e in moves] in ([], ["knockback"])
    assert all((e.from_pos["x"], e.from_pos["y"]) == (10, 0) for e in moves)
    assert s.combatants["b"].state.current_stun < 40          # still hit
    have = statuses_for(s, "b")
    assert IN_THE_AIR in have and PRONE not in have
    assert "dcv_factor" not in _ground_cv_modifiers(s, "b", "a", "ranged")
    mods = cv_modifiers_for(s, "b")
    assert mods.dcv_factor == 1.0
    assert knockback_dice_for(s, attack, TEMPLATE,
                              rolled_with_punch=False) == before - 1

    # c's Phase comes first, and he is still in the air through it.
    step = run_phase(result.encounter, Picks(_b_dives), roller=Dice(face=3),
                     on_unresolvable="raise")
    assert step.actor_id == "c"
    assert IN_THE_AIR in statuses_for(step.session, "b")
    # Then d's, and then his own, the one he gave up: he lands.
    while not [e for e in step.events
               if e.kind == "PhaseSpent" and e.combatant_id == "b"]:
        step = run_phase(step.encounter, Picks(_b_dives), roller=Dice(face=3),
                         on_unresolvable="raise")
    after = step.session
    have = statuses_for(after, "b")
    assert PRONE in have and IN_THE_AIR not in have
    assert knockback_dice_for(after, attack, TEMPLATE,
                              rolled_with_punch=False) == before


def test_dive_is_an_abort():
    enc, _ = _fight(4.0, SMALL)
    result = run_phase(enc, Picks(_b_dives), roller=Dice(face=1),
                       on_unresolvable="raise")
    aborts = [e for e in result.session.event_log
              if e.kind == "AbortDeclared" and e.combatant_id == "b"]
    assert [e.to_action for e in aborts] == ["dive_for_cover"]
    # His next Phase is forfeited: the loop spends it for him.
    nxt = run_phase(result.encounter, Picks(_b_dives), roller=Dice(face=1),
                    on_unresolvable="raise")
    spent = [e for e in nxt.events
             if e.kind == "PhaseSpent" and e.combatant_id == "b"]
    assert [e.reason for e in spent] == ["aborted"]
