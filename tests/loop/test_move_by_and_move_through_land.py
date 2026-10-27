"""A Move By or Move Through is an attack: a run, a roll, a blow, a recoil.

6E2 p.72. Until now both resolvers wrote a damage class into a payload and
nothing else happened: nobody moved, nobody rolled, nobody was hurt.

The scene: a (STR 20, Running 12m) at the origin, b 10m away along x.
Move By: (STR/2 = 10 -> 2d6) + 12/10 = 1d6 = 3d6. Move Through: (STR 20 ->
4d6) + 12/6 = 2d6 = 6d6. Every damage die is a 6 (2 BODY each).
"""
from __future__ import annotations

from shaped import (                                    # tests/loop/shaped.py
    TEMPLATE, Dice, Picks, armed, encounter_on, payloads, scene_with,
)
from kirby_combat.actions.velocity_maneuvers import damage_dice
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


def _fight(b_at=(10, 0, 0), **b_stats):
    scene = scene_with({"a": (0, 0, 0), "b": b_at})
    return encounter_on(scene,
                        armed("a", None, side=VILLAINS, dex=30, str_=20),
                        armed("b", None, side=HEROES, dex=10, **b_stats))


def _offer(kind):
    return LegalAction(action_id=f"{kind}:b", kind=kind, target_id="b",
                       power_xmlid=kind.upper(), power_name=kind, summary="")


def _sixes(n):
    """To-hit 3d6 = 9, then n damage dice of 6, then location and STUN x."""
    return Dice(face=3, queue=[[3, 3, 3], [6] * n])


def _vitals(session, who):
    st = session.combatants[who].state
    return st.current_stun, st.current_body


def test_the_dice_are_the_books():
    assert damage_dice(strength=20, velocity_mps=12, through=False) == (3, False)
    assert damage_dice(strength=20, velocity_mps=12, through=True) == (6, False)
    # Halved STR keeps the half die a remainder buys: STR 15 -> 7 -> 1d6,
    # STR 16 -> 8 -> 1 1/2d6 (kirby-cost `strike_dice`).
    assert damage_dice(strength=16, velocity_mps=0, through=False) == (1, True)


def test_a_move_by_is_offered_and_lands_through_run_phase():
    """Seam: offered by the menu, resolved by `run_phase`. Every die a 4: the
    roll is 12 against 11 + (9 - 2) - 5 = 13 and hits; 3d6 = 12 STUN, 3 BODY,
    and b's PD 4 leaves 8 / 0. a takes a third of the ROLL (4 / 1), against
    his own PD."""
    enc = _fight()
    chooser = Picks(lambda a, _s: a.kind == "move_by")
    result = run_phase(enc, chooser, roller=Dice(face=4), on_unresolvable="raise")
    assert result.kind == "move_by"
    s = result.session
    assert _vitals(s, "b") == (40 - 8, 12)
    recoil = payloads(s, kind="maneuver_recoil")[0]
    assert (recoil["stun_rolled"], recoil["body_rolled"]) == (4, 1)
    assert _vitals(s, "a") == (40, 12)          # his PD 4 takes it all


def test_a_move_by_recoil_is_a_third_of_the_roll_less_his_pd():
    """3d6 of 6s = 18 STUN, 6 BODY; b's PD 4 leaves 14 / 2. a takes 6 / 2 of
    the ROLL less PD 4: 2 STUN, 0 BODY (6E2 p.73: "he can apply his PD to
    reduce it"). The deleted driver took a third of the 14 / 2 that got
    through b instead, and gave a no defense."""
    enc = _fight()
    s = enc.sessions[0]
    out = resolve_chosen(s, s.combatants["a"], _offer("move_by"),
                         template=TEMPLATE, roller=_sixes(3))
    assert _vitals(out.session, "b") == (40 - 14, 12 - 2)
    assert _vitals(out.session, "a") == (40 - 2, 12)


def test_a_move_by_finishes_at_the_end_of_his_path():
    """6E2 p.72: "a Full Move past his target ... Hit or miss, the character
    finishes at the end of his movement path." 12m of Running from the
    origin, through where b stands, ends at x = 12."""
    enc = _fight()
    s = enc.sessions[0]
    out = resolve_chosen(s, s.combatants["a"], _offer("move_by"),
                         template=TEMPLATE, roller=_sixes(3))
    here = out.session.scene.combatant_positions["a"]
    assert round(here.x, 6) == 12.0 and round(here.y, 6) == 0.0


def test_a_move_through_that_knocks_him_back_costs_half():
    """6d6 of 6s = 36 STUN, 12 BODY; b takes 32 / 8 (and whatever landing
    from the Knockback costs him). a takes half the roll, 18 / 6, less PD 4
    = 14 / 2, and stops where he hit him (the labelled follow-through
    ruling)."""
    enc = _fight()
    s = enc.sessions[0]
    out = resolve_chosen(s, s.combatants["a"], _offer("move_through"),
                         template=TEMPLATE, roller=_sixes(6))
    hit = payloads(out.session, maneuver="move_through")[0]
    assert (hit["stun_dealt"], hit["body_dealt"]) == (32, 8)
    assert _vitals(out.session, "a") == (40 - 14, 12 - 2)
    assert round(out.session.scene.combatant_positions["a"].x, 6) == 9.0


def test_a_move_through_into_a_man_who_does_not_budge_costs_it_all():
    """6E2 p.72: "If the attack did no Knockdown or Knockback, then the
    attacker takes the full damage instead". b resists all Knockback: a
    takes 36 / 12 less PD 4 = 32 / 8."""
    enc = _fight(knockback_resistance=100)
    s = enc.sessions[0]
    out = resolve_chosen(s, s.combatants["a"], _offer("move_through"),
                         template=TEMPLATE, roller=_sixes(6))
    assert _vitals(out.session, "a") == (40 - 32, 12 - 8)


def test_the_maneuvers_dcv_holds_until_his_next_phase():
    """6E2 p.58: Move By -2 DCV, Move Through -3. Recorded through the same
    key a martial maneuver's DCV uses, so the attack door folds it."""
    from kirby_combat.actions.martial_arts import maneuver_dcv_delta

    enc = _fight()
    s = enc.sessions[0]
    by = resolve_chosen(s, s.combatants["a"], _offer("move_by"),
                        template=TEMPLATE, roller=_sixes(3))
    assert maneuver_dcv_delta(by.session, "a") == -2
    through = resolve_chosen(s, s.combatants["a"], _offer("move_through"),
                             template=TEMPLATE, roller=_sixes(6))
    assert maneuver_dcv_delta(through.session, "a") == -3


def test_a_charge_that_cannot_reach_him_is_refused():
    """The driver's `_velocity_charge_refusal`, kept: 30m off, 12m of
    Running, no contact --- no run, no blow."""
    enc = _fight(b_at=(30, 0, 0))
    s = enc.sessions[0]
    out = resolve_chosen(s, s.combatants["a"], _offer("move_through"),
                         template=TEMPLATE, roller=_sixes(6))
    p = payloads(out.session, kind="move_through")[0]
    assert p["out_of_reach"] is True and p["hit"] is False
    assert _vitals(out.session, "b") == (40, 12)
    assert out.session.scene.combatant_positions["a"].x == 0.0
