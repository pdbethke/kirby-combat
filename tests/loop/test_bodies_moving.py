"""Bodies moving: Knockback, falls, footing, Throws, climbing and getting up.

Every behaviour here goes through the live door (`resolve_chosen`, or
`run_phase(on_unresolvable="raise")`) and is read back off the session the
log produced: where the man stands, his STUN, and `statuses_for`. On
origin/main before this port, none of it happened -- a Blast computed a
Knockback distance into an audit string and the target never moved, nobody
fell, a Throw rolled 1d6 at a man and left him held, a climb went nowhere,
and Prone never cleared.

Dice are scripted (`FakeRoller`), one list per roll in the order the engine
draws them, so each test states the numbers it is about.
"""
from __future__ import annotations

import pytest
from conftest import blast  # tests/loop/conftest.py
from kirby_dice import FakeRoller
from kirby_world.scene import (
    AmbientConditions,
    Position,
    Scene,
    SceneBounds,
    Surface,
    Wall,
)

from kirby_combat.encounter import Encounter
from kirby_combat.enumeration import LegalAction, enumerate_actions
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.models import AttackPower
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.side import Side
from kirby_combat.statuses import FELL, PRONE, statuses_for
from kirby_combat.synthetic import synthetic_combatant
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()

#: One attack's dice, in `resolvers._attack_dice` order.
HIT = [1, 1, 1]
LOCATION = [3, 3, 3]
STUN_X = [1]


def _ground(x0=0.0, x1=100.0, z=0.0, *, sid="ground", precarious=False) -> Surface:
    return Surface(id=sid, name=sid, polygon_xy=[(x0, 0), (x1, 0), (x1, 100), (x0, 100)],
                   elevation_m=z, surface_type="ground", cover_level=0,
                   is_supporting=True, is_precarious=precarious)


def _scene(*, surfaces=None, walls=None, a=Position(10, 10, 0),
           t=Position(12, 10, 0), gravity=1.0) -> Scene:
    return Scene(
        id="lot", name="A Lot", bounds=SceneBounds(0, 0, 0, 100, 100, 50),
        surfaces=surfaces if surfaces is not None else [_ground()],
        walls=walls or [], hazards=[],
        ambient=AmbientConditions(gravity_scale=gravity),
        combatant_positions={"a": a, "t": t},
    )


def _attacker(*, str_=15, attacks=None, skills=None):
    return synthetic_combatant(
        id="a", name="a", ocv=9, dcv=5, spd=4, dex=20, str_=str_, con=20,
        pd=4, ed=4, max_stun=40, max_body=12, max_end=40,
        side=Side.named("heroes"), skills=skills,
        attacks=attacks if attacks is not None else [blast("a-eb", dice=6)],
    )


def _target(*, con=35, skills=None, dex=20):
    """CON 35, so the 32 STUN a 6d6 Blast of sixes gets through does not
    Stun him -- the saves below need a man who is not Stunned (6E2 p.119)."""
    return synthetic_combatant(
        id="t", name="t", ocv=9, dcv=5, spd=4, dex=dex, str_=15, con=con,
        pd=4, ed=4, max_stun=60, max_body=15, max_end=40,
        side=Side.named("villains"), skills=skills,
    )


def _session(scene, *, attacker=None, target=None, rolls=()) -> CombatSession:
    return CombatSession.create(
        id="s", combatants=[attacker or _attacker(), target or _target()],
        scene=scene, template=TEMPLATE, dice_roller=FakeRoller(list(rolls)),
    ).start()


def _blast_at_t(power=None) -> LegalAction:
    power = power or blast("a-eb", dice=6)
    return LegalAction(action_id="attack:t:a-eb", kind="attack", target_id="t",
                       power_xmlid=power.xmlid, power_name=power.name,
                       summary="Blast t", _attack_view=power)


def _resolve(session, action, rolls, actor="a"):
    return resolve_chosen(session, session.combatants[actor], action,
                          template=TEMPLATE, roller=FakeRoller(list(rolls)))


def _where(session, cid="t") -> tuple[float, float, float]:
    p = session.scene.combatant_positions[cid]
    return (round(p.x, 6), round(p.y, 6), round(p.z, 6))


def _moves(resolved, cid="t"):
    return [e.move_type for e in resolved.events
            if e.kind == "MovementResolved" and e.combatant_id == cid]


def _attack_row(resolved):
    return next(e.result_payload for e in resolved.events
                if e.kind == "ActionResolved" and e.result_payload.get("target_id") == "t")


# ---------------------------------------------------------------------------
# Knockback (6E2 p.116-119)
# ---------------------------------------------------------------------------

def test_knockback_moves_him_hurts_him_and_puts_him_down():
    """12 BODY rolled, 2d6 Knockback of 2: (12 - 2) x 2m = 20m (6E2 p.116),
    straight away from the attacker. Open ground: 1d6 per 4m, 5d6 of ones
    against PD 4 is 1 STUN (6E2 p.118). He ends on the ground."""
    session = _session(_scene())
    out = _resolve(session, _blast_at_t(),
                   [HIT, [6] * 6, LOCATION, STUN_X, [1, 1], [1] * 5])
    s = out.session
    assert _where(s) == (32.0, 10.0, 0.0)
    assert _moves(out) == ["knockback"]
    reasons = [(e.reason, e.stun) for e in out.events if e.kind == "VitalsChanged"
               and e.combatant_id == "t"]
    assert reasons == [("damage", -32), ("knockback", -1)]
    assert s.combatants["t"].state.current_stun == 60 - 32 - 1
    assert PRONE in statuses_for(s, "t")
    row = _attack_row(out)
    assert row[FELL] == ["t"]
    assert row["knockback"]["distance_m"] == 20.0


def test_knockback_uses_body_rolled_not_body_dealt():
    """6E2 p.116: "Use the total amount of BODY rolled on the attack dice,
    regardless of the target's defenses". Behind ED 20 the Blast does no
    damage at all and he still flies 20m."""
    target = synthetic_combatant(
        id="t", name="t", ocv=9, dcv=5, spd=4, dex=20, str_=15, con=35,
        pd=40, ed=40, max_stun=60, max_body=15, max_end=40,
        side=Side.named("villains"),
    )
    session = _session(_scene(), target=target)
    out = _resolve(session, _blast_at_t(),
                   [HIT, [6] * 6, LOCATION, STUN_X, [1, 1], [1] * 5])
    assert out.result.body_dealt == 0
    assert _where(out.session) == (32.0, 10.0, 0.0)


def test_into_a_wall_he_stops_and_takes_half_metres_of_the_whole_knockback():
    """6E2 p.118: 1d6 per 2m of the WHOLE 20m (10d6), at most the wall's
    PD + BODY (5 + 5 = 10d6); 20m is not MORE than 2 x 10, so the wall
    holds and he stops where he hit it. Breakfall cannot help against a
    wall, so his skill rolls nothing."""
    wall = Wall(id="w", name="brick", segment=(Position(20, 0, 0), Position(20, 100, 0)),
                height_m=5.0, body=5, def_value=5)
    session = _session(_scene(walls=[wall]), target=_target(skills={"BREAKFALL": 18}))
    out = _resolve(session, _blast_at_t(),
                   [HIT, [6] * 6, LOCATION, STUN_X, [1, 1], [1] * 10])
    s = out.session
    assert _where(s) == (20.0, 10.0, 0.0)
    kb = _attack_row(out)["knockback"]
    assert kb["wall_id"] == "w"
    assert kb["impact"]["dice"] == 10
    assert PRONE in statuses_for(s, "t")


def test_knocked_off_a_roof_he_falls_instead_of_hitting_the_ground():
    """The roof ends at x=15 and he is driven to x=32, 10m up: he falls
    10m, 1d6 per full 2m = 5d6 (6E2 p.142), and takes that INSTEAD of the
    ground impact (RULING on 6E2 p.118's "apply falling damage instead"; the
    driver charged both)."""
    roof = _ground(0, 15, 10.0, sid="roof")
    scene = _scene(surfaces=[_ground(), roof], a=Position(10, 10, 10),
                   t=Position(12, 10, 10))
    out = _resolve(_session(scene), _blast_at_t(),
                   [HIT, [6] * 6, LOCATION, STUN_X, [1, 1], [3] * 5])
    s = out.session
    assert _where(s) == (32.0, 10.0, 0.0)
    assert _moves(out) == ["knockback", "fall"]
    reasons = [e.reason for e in out.events if e.kind == "VitalsChanged"
               and e.combatant_id == "t"]
    assert reasons == ["damage", "falling"]
    assert _attack_row(out)["knockback"]["fall"]["damage_dice"] == 5
    assert PRONE in statuses_for(s, "t")


def test_breakfall_lands_him_on_his_feet_on_open_ground():
    """6E2 p.119: Breakfall at -1 per 4m (20m: -5) -- 14 less 5 is 9, and a
    roll of 3 makes it. No damage, and he is not Prone."""
    session = _session(_scene(), target=_target(skills={"BREAKFALL": 14}))
    out = _resolve(session, _blast_at_t(),
                   [HIT, [6] * 6, LOCATION, STUN_X, [1, 1], [1, 1, 1]])
    s = out.session
    kb = _attack_row(out)["knockback"]
    assert kb["breakfall"]["target"] == 9 and kb["breakfall"]["made"]
    assert "impact" not in kb
    assert _where(s) == (32.0, 10.0, 0.0)
    assert PRONE not in statuses_for(s, "t")


def test_a_zero_result_knocks_him_down_where_he_stands():
    """6E2 p.116: "If the result is 0, the defender is Knocked Down." 12
    BODY against a roll of 12: no distance, no damage, on the ground."""
    session = _session(_scene())
    out = _resolve(session, _blast_at_t(),
                   [HIT, [6] * 6, LOCATION, STUN_X, [6, 6]])
    s = out.session
    assert _where(s) == (12.0, 10.0, 0.0)
    assert _attack_row(out)["knockback"]["knocked_down"] is True
    assert PRONE in statuses_for(s, "t")


def test_a_killing_attack_rolls_another_knockback_die():
    """6E2 p.117's table: "Attack was a Killing Damage attack: +1d6". The
    scripted pool is three dice; a pool of two would fail the roller."""
    rka = AttackPower(xmlid="RKA", name="Gun", damage_dice=2, half_die=False,
                      plus_one=False, damage_type="killing", defense_type="pd",
                      range_m=100, uses_str=False, str_min=0, armor_piercing=0,
                      penetrating=0, increased_stun_mult=0, source_id="a-gun",
                      is_ranged=True)
    session = _session(_scene(), attacker=_attacker(attacks=[rka]))
    out = _resolve(session, _blast_at_t(rka),
                   [HIT, [6, 6], LOCATION, STUN_X, [6, 6, 6]])
    assert "knockback" not in _attack_row(out)          # 12 BODY - 18: none
    assert _where(out.session) == (12.0, 10.0, 0.0)


def test_no_knockback_rolls_nothing_and_moves_nobody():
    """6E1 p.147: No Knockback "never does Knockback". The pool is the
    attack's own four rolls -- one more draw would exhaust it."""
    from dataclasses import replace

    nokb = replace(blast("a-eb", dice=6), no_knockback=True)
    session = _session(_scene(), attacker=_attacker(attacks=[nokb]))
    out = _resolve(session, _blast_at_t(nokb), [HIT, [6] * 6, LOCATION, STUN_X])
    assert _where(out.session) == (12.0, 10.0, 0.0)
    assert PRONE not in statuses_for(out.session, "t")


def test_a_man_in_the_air_flies_back_and_takes_nothing():
    """In the air: -1d6 Knockback (6E2 p.117), so one die; hitting nothing
    he "takes no damage at all" (p.118). He stays at his height and is not
    lying on anything, so he is not Prone (RULING)."""
    scene = _scene(t=Position(12, 10, 5))
    out = _resolve(_session(scene), _blast_at_t(),
                   [HIT, [6] * 6, LOCATION, STUN_X, [2]])
    s = out.session
    assert _where(s) == (32.0, 10.0, 5.0)              # (12 - 2) x 2m
    assert _moves(out) == ["knockback"]
    assert PRONE not in statuses_for(s, "t")


def test_knockback_is_off_when_the_campaign_turns_it_off():
    from dataclasses import replace

    template = replace(TEMPLATE, use_knockback=False)
    session = _session(_scene())
    out = resolve_chosen(session, session.combatants["a"], _blast_at_t(),
                         template=template,
                         roller=FakeRoller([HIT, [6] * 6, LOCATION, STUN_X]))
    assert _where(out.session) == (12.0, 10.0, 0.0)


def test_knockback_runs_through_run_phase():
    """The whole path: the loop offers the Blast, the chooser takes it, the
    engine moves him, and the Phase's events say so."""
    session = _session(_scene(), rolls=[])
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    roller = FakeRoller([[3, 3, 3], [3, 3, 3],          # 6E2 p.21 DEX tie-break
                         HIT, [6] * 6, LOCATION, STUN_X, [1, 1], [1] * 5])
    enc = enc.run_segment(roller=lambda: roller.roll_dice(3))

    class TakeTheBlast:
        def choose(self, situation):
            if situation.actor.id != "a":
                return next(x.action_id for x in situation.menu if x.kind == "dodge")
            return next(x.action_id for x in situation.menu
                        if x.kind == "attack" and x.target_id == "t")

    phase = run_phase(enc, TakeTheBlast(), roller=roller, on_unresolvable="raise")
    if phase.actor_id != "a":
        phase = run_phase(phase.encounter, TakeTheBlast(), roller=roller,
                          on_unresolvable="raise")
    s = phase.session
    assert _where(s) == (32.0, 10.0, 0.0)
    assert PRONE in s.statuses["t"], "the Phase's status row says he is down"


# ---------------------------------------------------------------------------
# Prone: what it costs, and getting up (6E2 p.51, p.129, 6E1 p.68)
# ---------------------------------------------------------------------------

def _knocked_down():
    session = _session(_scene())
    return _resolve(session, _blast_at_t(),
                    [HIT, [6] * 6, LOCATION, STUN_X, [6, 6]]).session


def test_prone_halves_his_dcv_and_costs_him_two_ocv():
    """6E2 p.129: half DCV "when attacked by non-prone characters", and
    "attacking from the ground imposes a -2 OCV penalty"."""
    from kirby_combat.cv_modifiers import effective_dcv_for, effective_ocv_for

    s = _knocked_down()
    assert effective_dcv_for(s, "t", against="a", combat_type="ranged") == 3   # ceil(5/2)
    assert effective_ocv_for(s, "t", against="a", combat_type="ranged") == 9 - 2
    assert effective_dcv_for(s, "a", against="t", combat_type="ranged") == 5


def test_stand_up_is_offered_and_clears_prone():
    s = _knocked_down()
    t = s.combatants["t"]
    menu = enumerate_actions(t, [s.combatants["a"]], prone=True)
    offer = next(a for a in menu if a.kind == "stand_up")
    out = _resolve(s, offer, [], actor="t")
    assert PRONE not in statuses_for(out.session, "t")
    assert any(e.kind == "StatusEffectsChanged" and PRONE in e.removed
               for e in out.events)
    standing = enumerate_actions(t, [s.combatants["a"]], prone=False)
    assert "stand_up" not in {a.kind for a in standing}


def test_breakfall_stands_him_up_for_nothing_at_the_top_of_his_phase():
    """6E1 p.68: "If the roll succeeds, the character gets to his feet as a
    Zero Phase Action" -- and still has his Phase."""
    from kirby_combat.standing import breakfall_to_feet

    session = _session(_scene(), target=_target(skills={"BREAKFALL": 14}))
    # Knocked down: no penalty on the save, and he fails it (18).
    s = _resolve(session, _blast_at_t(),
                 [HIT, [6] * 6, LOCATION, STUN_X, [6, 6], [6, 6, 6]]).session
    assert PRONE in statuses_for(s, "t")
    up = breakfall_to_feet(s, "t", FakeRoller([[1, 1, 1]]))
    assert PRONE not in statuses_for(up, "t")
    stayed = breakfall_to_feet(s, "t", FakeRoller([[6, 6, 6]]))
    assert PRONE in statuses_for(stayed, "t")


# ---------------------------------------------------------------------------
# Footing on a narrow perch
# ---------------------------------------------------------------------------

def _on_a_ledge(**kw):
    ledge = _ground(11, 13, 5.0, sid="ledge", precarious=True)
    return _scene(surfaces=[_ground(), ledge], t=Position(12, 10, 5), **kw)


def test_a_ledge_costs_two_dcv():
    """6E2 p.39: "On a narrow surface (tightrope, ledge), DCV = -2". The
    same perch, flagged and not: the difference is the -2."""
    from kirby_combat.cv_modifiers import effective_dcv_for

    def dcv(precarious):
        ledge = _ground(11, 13, 5.0, sid="ledge", precarious=precarious)
        s = _session(_scene(surfaces=[_ground(), ledge], t=Position(12, 10, 5),
                            a=Position(12.5, 10, 5)))
        return effective_dcv_for(s, "t", against="a", combat_type="hth")

    assert dcv(False) - dcv(True) == 2


def test_hit_on_a_ledge_he_can_lose_his_footing_and_fall():
    """A Blast of ones (no BODY, so no Knockback is owed) lands; his DEX
    Roll (9 + 20/5 = 13) fails on 18 and he falls 5m: 2d6 (6E2 p.142)."""
    s = _session(_on_a_ledge())
    out = _resolve(s, _blast_at_t(),
                   [HIT, [1] * 6, LOCATION, STUN_X, [6, 6, 6], [3, 3]])
    row = _attack_row(out)
    assert row["footing"]["target"] == 13 and not row["footing"]["kept_footing"]
    assert _where(out.session) == (12.0, 10.0, 0.0)
    assert PRONE in statuses_for(out.session, "t")


def test_acrobatics_keeps_him_on_the_ledge():
    """6E1 p.65: Acrobatics "can also retain his balance ... on narrow or
    difficult surfaces". The better of it and the DEX Roll is rolled."""
    s = _session(_on_a_ledge(), target=_target(skills={"ACROBATICS": 16}))
    out = _resolve(s, _blast_at_t(), [HIT, [1] * 6, LOCATION, STUN_X, [5, 5, 5]])
    row = _attack_row(out)
    assert row["footing"]["target"] == 16 and row["footing"]["kept_footing"]
    assert _where(out.session) == (12.0, 10.0, 5.0)


# ---------------------------------------------------------------------------
# Throwing the man you are holding (6E2 p.64, p.83-85)
# ---------------------------------------------------------------------------

def _close(**kw):
    """A grabber has his man within Reach (1m, 6E2 p.56)."""
    return _scene(t=Position(11, 10, kw.pop("z", 0.0)), **kw)


def _held(scene, *, attacker=None, target=None):
    from kirby_combat.actions.grab import Grab

    s = _session(scene, attacker=attacker, target=target)
    s, grab = Grab.declare_and_resolve(
        s, attacker_id="a", target_id="t", attacker_str=15, target_str=15,
        attacker_ocv=9, target_dcv=5, attack_roll=3,
    )
    assert grab.success and Grab.is_grabbed(s, "t") == (True, "a")
    return s


_THROW = LegalAction(action_id="throw:t", kind="throw", target_id="t",
                     power_xmlid="THROW", power_name="Throw", summary="Throw t")


def test_a_throw_hurts_him_moves_him_puts_him_down_and_ends_the_hold():
    """STR 15: 3d6 Normal (the bare Strike, p.64), thrown a Standing Throw's
    distance for 5 extra STR -- 4m (p.83) -- landing prone (p.84). The hold
    ends."""
    from kirby_combat.actions.grab import Grab

    s = _held(_close())
    out = _resolve(s, _THROW, [HIT, [6, 6, 6], LOCATION, STUN_X])
    after = out.session
    assert out.result.hit
    assert out.result.stun_dealt == 18 - 4
    assert _where(after) == (15.0, 10.0, 0.0)
    assert _moves(out) == ["thrown"]
    assert PRONE in statuses_for(after, "t")
    assert Grab.is_grabbed(after, "t") == (False, None)


def test_breakfall_halves_a_throw():
    """6E2 p.85: "reduce the damage taken from a Throw by half if he makes a
    Breakfall roll at -1 for every 2d6" -- 3d6 is -1."""
    s = _held(_close(), target=_target(skills={"BREAKFALL": 14}))
    out = _resolve(s, _THROW, [[1, 1, 1], HIT, [6, 6, 6], LOCATION, STUN_X])
    assert out.result.stun_dealt == (18 - 4) // 2
    assert _attack_row(out)["breakfall"]["target"] == 13


def test_a_missed_throw_lets_go_and_moves_nobody():
    """6E2 p.84: a failed Throw does nothing to him; RULING, he "got out of
    the Thrower's grasp and is still within Reach"."""
    from kirby_combat.actions.grab import Grab

    s = _held(_close())
    out = _resolve(s, _THROW, [[6, 6, 6], [6, 6, 6], LOCATION, STUN_X])
    assert not out.result.hit
    assert _where(out.session) == (11.0, 10.0, 0.0)
    assert PRONE not in statuses_for(out.session, "t")
    assert Grab.is_grabbed(out.session, "t") == (False, None)


def test_thrown_off_a_roof_he_falls():
    roof = _ground(0, 14, 6.0, sid="roof")
    scene = _scene(surfaces=[_ground(), roof], a=Position(10, 10, 6),
                   t=Position(11, 10, 6))
    out = _resolve(_held(scene), _THROW, [HIT, [1, 1, 1], LOCATION, STUN_X, [1, 1, 1]])
    assert _where(out.session) == (15.0, 10.0, 0.0)
    assert _moves(out) == ["thrown", "fall"]


def test_a_throw_into_a_wall_is_capped_at_its_pd_plus_body():
    """p.84: "up to a maximum of the PD + BODY of the surface (or object)
    he's Thrown into" -- a 1 PD / 1 BODY board caps 3d6 at 2d6."""
    wall = Wall(id="w", name="board", segment=(Position(14, 0, 0), Position(14, 100, 0)),
                height_m=3.0, body=1, def_value=1)
    out = _resolve(_held(_close(walls=[wall])), _THROW, [HIT, [6, 6], LOCATION, STUN_X])
    assert out.result.stun_dealt == 12 - 4
    assert _where(out.session) == (14.0, 10.0, 0.0)


def test_throw_offer_names_an_attack_roll_not_an_auto_hit():
    s = _held(_close())
    a = s.combatants["a"]
    menu = enumerate_actions(a, [s.combatants["t"]], has_scene=True, scene=s.scene,
                             distances={"t": 1.0}, held_target_ids=frozenset({"t"}))
    offer = next(x for x in menu if x.kind == "throw")
    assert "Attack Roll" in offer.summary and "auto-hits" not in offer.summary


# ---------------------------------------------------------------------------
# Climbing (6E1 p.70)
# ---------------------------------------------------------------------------

def _cliff(difficulty: int) -> Wall:
    return Wall(id="cliff", name="cliff", segment=(Position(13, 0, 0), Position(13, 100, 0)),
                height_m=10.0, climb_difficulty=difficulty, walkable_width_m=1.0)


def _climb_offer(s, kind="climb"):
    a = s.combatants["a"]
    menu = enumerate_actions(a, [s.combatants["t"]], has_scene=True, scene=s.scene,
                             distances={"t": 50.0})
    return next(x for x in menu if x.kind == kind)


def _climber(at=Position(13, 10, 0), difficulty=2, skill=12):
    scene = _scene(walls=[_cliff(difficulty)], a=at, t=Position(60, 60, 0))
    return _session(scene, attacker=_attacker(skills={"CLIMBING": skill} if skill else None))


def test_a_climb_rolls_and_goes_up():
    """A difficult face is a Climbing roll at minus its difficulty (12-2:
    10); a 9 makes it and he is 2m up the face. (The 18 after it is his
    separate roll to shed the climbing penalties, 6E2 p.49, which fails.)"""
    s = _climber()
    out = _resolve(s, _climb_offer(s), [[3, 3, 3], [6, 6, 6]])
    assert out.session.scene.combatant_positions["a"].z == pytest.approx(2.0)
    assert out.events[-1].result_payload["climbing_roll"]["target"] == 10


def test_a_failed_climb_goes_nowhere():
    s = _climber()
    out = _resolve(s, _climb_offer(s), [[4, 4, 4]])   # 12 misses 10 by 2
    assert out.session.scene.combatant_positions["a"].z == 0.0


def test_a_spectacular_miss_off_the_ground_is_a_fall():
    """Missing by 5 or more (RULING on 6E1 p.70's "spectacularly bad") from
    4m up: he falls 4m, 2d6 (6E2 p.142), and lands prone."""
    s = _climber(at=Position(13, 10, 4), difficulty=6)
    out = _resolve(s, _climb_offer(s), [[5, 5, 5], [2, 2]])   # 15 against 6
    assert out.session.scene.combatant_positions["a"].z == 0.0
    assert PRONE in statuses_for(out.session, "a")
    assert out.events[-1].result_payload[FELL] == ["a"]


def test_an_ordinary_face_needs_no_roll():
    """6E1 p.70: "Most characters can climb ordinary things (like ladders)
    without a Skill." Only his separate roll to shed the -1 DCV (6E2 p.49) is
    scripted, so a climbing roll would fail the test -- and that holds for a
    man who HAS the Skill too (the driver made him roll)."""
    s = _climber(difficulty=0)
    out = _resolve(s, _climb_offer(s), [[6, 6, 6]])
    assert out.events[-1].result_payload["climbing_roll"] is None
    assert out.session.scene.combatant_positions["a"].z == pytest.approx(2.0)


def test_hurrying_needs_the_skill():
    """6E1 p.70's +2m is "per -3 penalty to the Climbing roll": nobody
    without the roll is offered it."""
    s = _climber(difficulty=0, skill=None)
    a = s.combatants["a"]
    kinds = {x.kind for x in enumerate_actions(a, [s.combatants["t"]], has_scene=True,
                                               scene=s.scene, distances={"t": 50.0})}
    assert "climb" in kinds and "climb_fast" not in kinds
