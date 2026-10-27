"""Follow-up K2b: the pieces #10 (bodies moving) left unbuilt.

Through the wall (6E2 p.118), Double Knockback (6E1 p.336), Does Knockback
(6E1 p.335), underwater (6E2 p.117, p.170), Clinging (6E1 p.184), Rolling
With The Punch (6E2 p.90), the Thrower acting first and the Acrobatics roll
to keep one's feet (6E2 p.84-85), a Thrown man's fall checked for Stun on
its own (6E2 p.105), and the climbing penalties (6E2 p.48-49). Each goes
through `resolve_chosen` or `run_phase(on_unresolvable="raise")`, and each
fails on origin/main.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from conftest import blast, fighter, encounter_of  # tests/loop/conftest.py
from kirby_dice import RandomRoller
from kirby_world.scene import Position, Surface, Wall

from test_bodies_moving import (  # tests/loop/test_bodies_moving.py
    HIT, LOCATION, STUN_X, TEMPLATE, _THROW, _attack_row, _attacker, _blast_at_t,
    _close, _climb_offer, _climber, _ground, _held, _moves, _resolve, _scene,
    _session, _target, _where,
)
from test_reactions_and_concealment import Script  # tests/loop/

from kirby_combat.constructs import damage_by_object
from kirby_combat.cv_modifiers import effective_dcv_for
from kirby_combat.encounter import Encounter
from kirby_combat.loop import run_phase
from kirby_combat.side import Side
from kirby_combat.statuses import FELL, PRONE, STUNNED, statuses_for
from kirby_combat.synthetic import synthetic_combatant


# ---------------------------------------------------------------------------
# Through the wall (6E2 p.118)
# ---------------------------------------------------------------------------

def test_a_man_knocked_through_a_wall_shatters_it_and_flies_on():
    """20m of Knockback into a 6 PD / 2 BODY wall 2m behind him: more than
    2 x 8, so he takes 8d6, the wall shatters, and he "continues 22-2-8"
    (the page's own arithmetic) -- here 20 - 2 - 8 = 10m more, to x=24, and
    lands on open ground for 10m: 2d6 (1d6 per 4m)."""
    wall = Wall(id="w", name="board fence", segment=(Position(14, 0, 0), Position(14, 100, 0)),
                height_m=1.0, body=2, def_value=6)
    out = _resolve(_session(_scene(walls=[wall])), _blast_at_t(),
                   [HIT, [6] * 6, LOCATION, STUN_X, [1, 1], [1] * 8, [1, 1]])
    s = out.session
    assert _where(s) == (24.0, 10.0, 0.0)
    assert _moves(out) == ["knockback", "knockback"]
    kb = _attack_row(out)["knockback"]
    struck = kb["walls"][0]
    assert struck["wall_id"] == "w" and struck["shattered"] and struck["destroyed"]
    assert struck["impact"]["dice"] == 8
    assert kb["impact"]["dice"] == 2              # the ground, after the hole
    # The structure took damage too, and the fight remembers it.
    assert damage_by_object(s)["w"] == 2
    assert all(w.id != "w" for w in s.scene.walls)
    assert PRONE in statuses_for(s, "t")


def test_a_wall_he_does_not_shatter_still_takes_the_impact():
    """6E2 p.118: "both he and the structure take damage". 20m into a 5/5
    wall holds (not MORE than 2 x 10); the 10d6 of twos he takes is 10 BODY,
    5 through the wall's DEF 5 (6E2 p.172) -- which is all its BODY."""
    wall = Wall(id="w", name="brick", segment=(Position(20, 0, 0), Position(20, 100, 0)),
                height_m=1.0, body=5, def_value=5)
    out = _resolve(_session(_scene(walls=[wall])), _blast_at_t(),
                   [HIT, [6] * 6, LOCATION, STUN_X, [1, 1], [2] * 10])
    struck = _attack_row(out)["knockback"]["walls"][0]
    assert not struck["shattered"] and struck["body_dealt"] == 5
    assert _where(out.session) == (20.0, 10.0, 0.0)
    assert damage_by_object(out.session)["w"] == 5


# ---------------------------------------------------------------------------
# What changes the Knockback roll (6E2 p.117, 6E1 p.335-336)
# ---------------------------------------------------------------------------

def test_double_knockback_doubles_the_body_before_the_roll():
    """6E1 p.336: 3d6 of sixes is 6 BODY, doubled to 12, less a 2 on the
    Knockback roll: (12 - 2) x 2m = 20m. Without it, 8m."""
    power = replace(blast("a-eb", dice=3), double_knockback=True)
    attacker = _attacker(attacks=[power])
    out = _resolve(_session(_scene(), attacker=attacker), _blast_at_t(power),
                   [HIT, [6] * 3, LOCATION, STUN_X, [1, 1], [1] * 5])
    assert _attack_row(out)["knockback"]["distance_m"] == 20.0
    assert _where(out.session) == (32.0, 10.0, 0.0)


def test_does_knockback_lets_a_no_body_attack_knock_him_back():
    """6E1 p.335: an AVAD does no BODY and so no Knockback (6E2 p.116),
    unless bought with Does Knockback: then "count the Normal Damage BODY
    on the effect dice". 6d6 of sixes counts 12."""
    avad = replace(blast("a-eb", dice=6), avad=True, avad_defense="FORCEFIELD",
                   does_knockback=True)
    out = _resolve(_session(_scene(), attacker=_attacker(attacks=[avad])),
                   _blast_at_t(avad),
                   [HIT, [6] * 6, LOCATION, STUN_X, [1, 1], [1] * 5])
    assert out.result.body_dealt == 0
    assert _attack_row(out)["knockback"]["distance_m"] == 20.0


def _water_under_t() -> Surface:
    return Surface(id="pond", name="pond", polygon_xy=[(11, 9), (13, 9), (13, 11), (11, 11)],
                   elevation_m=0.0, surface_type="water", cover_level=0,
                   is_supporting=True)


def test_underwater_adds_a_die_to_the_knockback_roll():
    """6E2 p.117 / p.170: +1d6 for a target in the water. Three dice rolled."""
    scene = _scene(surfaces=[_ground(), _water_under_t()])
    out = _resolve(_session(scene), _blast_at_t(),
                   [HIT, [6] * 6, LOCATION, STUN_X, [1, 1, 1], [1] * 4])
    assert _attack_row(out)["knockback"]["dice"] == 3
    assert _attack_row(out)["knockback"]["distance_m"] == 18.0


def _clinger(*limitations):
    t = _target()
    t.hero.powers.append(SimpleNamespace(
        xmlid="CLINGING", id="cling", name="Wall-Crawling",
        assigned_modifiers=[SimpleNamespace(xmlid=x) for x in limitations]))
    return t


def test_clinging_adds_a_die_to_the_knockback_roll():
    """6E1 p.184: "A character using Clinging subtracts an extra 1d6 from all
    Knockback rolls, as long as he's in contact with a solid surface"."""
    out = _resolve(_session(_scene(), target=_clinger()), _blast_at_t(),
                   [HIT, [6] * 6, LOCATION, STUN_X, [1, 1, 1], [1] * 4])
    assert _attack_row(out)["knockback"]["dice"] == 3


def test_clinging_that_cannot_resist_knockback_adds_nothing():
    out = _resolve(_session(_scene(), target=_clinger("CANNOTRESISTKB")), _blast_at_t(),
                   [HIT, [6] * 6, LOCATION, STUN_X, [1, 1], [1] * 5])
    assert _attack_row(out)["knockback"]["dice"] == 2


# ---------------------------------------------------------------------------
# Rolling With The Punch (6E2 p.90)
# ---------------------------------------------------------------------------

class Ones(RandomRoller):
    def roll_dice(self, n, sides=6):
        return [1] * n


class Sixes(RandomRoller):
    def roll_dice(self, n, sides=6):
        return [6] * n


def _punch_duel():
    a = fighter("a", side=Side.named("heroes"), dex=30, dice=8)
    d = fighter("d", side=Side.named("villains"), dex=10)
    a.attacks[:] = [replace(blast("a-fist", dice=8, range_m=0), no_knockback=False)]
    return encounter_of(a, d)


def _blow_on(events):
    return next(e.result_payload for e in events if e.kind == "ActionResolved"
                and e.result_payload.get("target_id") == "d"
                and "hit" in e.result_payload)


def test_rolling_with_the_punch_halves_what_he_takes():
    """He rolls OCV-2 against the attacker's OCV and makes it on a 3: he takes
    half the STUN and BODY after defenses, and gives up his next Phase."""
    rolled = run_phase(_punch_duel(), Script(own={"a": ("attack", "d")},
                                             react={"d": "roll_with_punch"}),
                       roller=Ones(seed=1), on_unresolvable="raise")
    took = run_phase(_punch_duel(), Script(own={"a": ("attack", "d")}),
                     roller=Ones(seed=1), on_unresolvable="raise")
    with_it, without = _blow_on(rolled.events), _blow_on(took.events)
    assert with_it["rolled_with_punch"]["success"]
    assert with_it["stun_dealt"] == max(without["stun_dealt"] // 2,
                                        with_it["body_dealt"])
    aborts = [(e.combatant_id, e.to_action) for e in rolled.events
              if e.kind == "AbortDeclared"]
    assert aborts == [("d", "roll_with_punch")]


def test_rolling_with_the_punch_costs_nothing_when_the_blow_misses():
    """RULING: the choice is made before the roll, and is conditional --
    p.90 lets him decide after the blow lands. Every die a six: the blow
    misses, and no Abort is declared."""
    out = run_phase(_punch_duel(), Script(own={"a": ("attack", "d")},
                                          react={"d": "roll_with_punch"}),
                    roller=Sixes(seed=1), on_unresolvable="raise")
    assert not _blow_on(out.events)["hit"]
    assert not [e for e in out.events if e.kind == "AbortDeclared"]


def test_rolling_with_the_punch_takes_a_die_off_the_knockback():
    """p.90: "the attacker rolls one less die for Knockback"."""
    from kirby_combat.actions.reactive.roll_with_punch import declare_ready
    from kirby_combat.enumeration import LegalAction

    fist = blast("a-eb", dice=6, range_m=0)
    s = _session(_scene(t=Position(11, 10, 0)), attacker=_attacker(attacks=[fist]))
    s = declare_ready(s, "t", "a")
    punch = LegalAction(action_id="attack:t:a-eb", kind="attack", target_id="t",
                        power_xmlid=fist.xmlid, power_name=fist.name,
                        summary="punch t", _attack_view=fist)
    out = _resolve(s, punch, [HIT, [6] * 6, LOCATION, STUN_X, [3, 3, 3], [1], [1] * 5])
    kb = _attack_row(out)["knockback"]
    assert _attack_row(out)["rolled_with_punch"]["success"]
    assert kb["dice"] == 1 and kb["distance_m"] == 22.0


# ---------------------------------------------------------------------------
# What a Throw does besides the damage (6E2 p.84-85)
# ---------------------------------------------------------------------------

def test_the_thrower_acts_first_when_their_next_phases_share_a_segment():
    """6E2 p.84: both SPD 4, so both next act in Segment 3 of Turn 2, and the
    Thrower goes first "regardless of relative DEX" -- here DEX 20 against
    the thrown man's 30."""
    s = _held(_close(), target=_target(dex=30))
    out = _resolve(s, _THROW, [HIT, [1, 1, 1], LOCATION, STUN_X])
    assert _attack_row(out)["thrower_first"] == [2, 3]
    ordered = Encounter(id="e", turn=2, segment=3, sessions=[out.session]).run_segment(
        roller=lambda: [3, 3, 3])
    order = [slot.combatant_id for slot in ordered.scene_acting_order]
    assert order == ["a", "t"]


def test_the_priority_lapses_when_their_next_phases_do_not_share_a_segment():
    slow = synthetic_combatant(id="t", name="t", ocv=9, dcv=5, spd=3, dex=30,
                               str_=15, con=35, pd=4, ed=4, max_stun=60,
                               max_body=15, max_end=40, side=Side.named("villains"))
    out = _resolve(_held(_close(), target=slow), _THROW, [HIT, [1, 1, 1], LOCATION, STUN_X])
    assert _attack_row(out)["thrower_first"] is None


def test_acrobatics_at_minus_three_keeps_his_feet():
    """6E2 p.85: "He can keep his feet (or land on them) if he succeeds with
    an Acrobatics roll at -3. However, this doesn't prevent him from taking
    damage"."""
    s = _held(_close(), target=_target(skills={"ACROBATICS": 14}))
    out = _resolve(s, _THROW, [[3, 3, 3], HIT, [6, 6, 6], LOCATION, STUN_X])
    row = _attack_row(out)
    assert row["acrobatics"]["target"] == 11 and row["acrobatics"]["made"]
    assert row[FELL] == []
    assert out.result.stun_dealt == 18 - 4
    assert PRONE not in statuses_for(out.session, "t")


def test_a_thrown_mans_fall_can_stun_him_on_its_own():
    """Thrown off a 20m roof: the Throw's 1d6 of ones does nothing, the 10d6
    fall (6E2 p.142) of sixes beats CON 35 alone -- its own instance of
    damage (6E2 p.105) -- and he is Stunned."""
    roof = _ground(0, 14, 20.0, sid="roof")
    scene = _scene(surfaces=[_ground(), roof], a=Position(10, 10, 20),
                   t=Position(11, 10, 20))
    out = _resolve(_held(scene), _THROW, [HIT, [1, 1, 1], LOCATION, STUN_X, [6] * 10])
    landing = next(e.result_payload for e in out.events if e.kind == "ActionResolved"
                   and e.result_payload.get("kind") == "landing")
    assert landing["status_changes"] == ["Stunned"]
    assert STUNNED in statuses_for(out.session, "t")


# ---------------------------------------------------------------------------
# On the wall (6E2 p.48-49)
# ---------------------------------------------------------------------------

def test_a_man_on_a_difficult_face_is_at_half_dcv():
    s = _climber()                                   # difficulty 2, Climbing 12-
    out = _resolve(s, _climb_offer(s), [[3, 3, 3], [6, 6, 6]])
    assert out.session.scene.combatant_positions["a"].z == pytest.approx(2.0)
    from kirby_combat.cv_modifiers import apply_cv_factor

    assert effective_dcv_for(out.session, "a", against="t") == apply_cv_factor(5, 0.5)


def test_an_easy_face_is_minus_one_dcv():
    s = _climber(difficulty=0)
    out = _resolve(s, _climb_offer(s), [[6, 6, 6]])
    assert effective_dcv_for(out.session, "a", against="t") == 5 - 1


def test_his_climbing_roll_sheds_the_penalties():
    """6E2 p.49: "a character can eliminate these penalties with a successful
    Climbing roll" -- the 9 after his climb makes it."""
    s = _climber()
    out = _resolve(s, _climb_offer(s), [[3, 3, 3], [3, 3, 3]])
    assert out.events[-1].result_payload["penalties_roll"]["made"]
    assert effective_dcv_for(out.session, "a", against="t") == 5


def test_from_a_difficult_face_his_attacks_lose_two_dcs():
    """6E2 p.49: "subtract 2 DCs from all attacks". His 6d6 Blast fires 4d6."""
    s = _climber()
    out = _resolve(s, _climb_offer(s), [[3, 3, 3], [6, 6, 6]])
    shot = _resolve(out.session, replace(_blast_at_t(), target_id="t"),
                    [HIT, [6] * 6, LOCATION, STUN_X, [6, 6]])
    assert shot.result.damage.stun == 4 * 6


def test_a_man_knocked_off_the_wall_is_no_longer_on_it():
    from kirby_combat.climbing_state import on_the_wall

    s = _climber()
    out = _resolve(s, _climb_offer(s), [[3, 3, 3], [6, 6, 6]])
    assert on_the_wall(out.session, "a") is not None
    from kirby_combat.impact import _record_move

    here = out.session.scene.combatant_positions["a"]
    moved = _record_move(out.session, "a", here, Position(20, 10, 0),
                         move_type="knockback", distance_m=7.0)
    assert on_the_wall(moved, "a") is None


def test_a_long_fall_is_read_off_the_velocity_not_capped():
    """6E2 p.142: a Long Fall does 1d6 per 2m/Segment of velocity at impact,
    and velocity tops out at 60m -- so 30d6, not the 20d6 kirby-world 0.1.0
    capped at. `impact.fall` asks `kirby_world.resolve_fall` (>= 0.1.1)."""
    from kirby_combat.impact import fall

    roof = _ground(0, 100, 45.0, sid="tower")
    scene = replace(_scene(surfaces=[_ground(), roof], t=Position(12, 10, 45)),
                    bounds=replace(_scene().bounds, max_z=300))
    s = _session(scene)
    edge = Position(12, 10, 245)
    s2, landed = fall(s, "t", edge, roller=__import__("kirby_dice").FakeRoller([[1] * 30]),
                      template=TEMPLATE)
    assert landed["fall_distance_m"] == 200.0 and landed["damage_dice"] == 30
