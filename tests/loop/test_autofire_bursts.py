"""Autofire: one roll, several hits; END and Charges per shot; Knockback once.

6E2 p.44 (one target): "If the Attack Roll succeeds, the character hits the
target one time; in addition, for every full 2 points by which the Attack
Roll succeeds, he hits the target an additional time"; "Each Autofire shot
counts as a separate attack for purposes of determining if the target's
Stunned". 6E2 p.44 (several): "-1 OCV penalty for each 2m in the line ... a
separate Attack Roll for each target ... each target can only get hit one
time". 6E1 p.329: END "for each shot"; "Each hit ... applies separately
against the target's defenses"; Knockback from "the BODY of the largest
attack and add +1 BODY for each additional hit". 6E2 p.45: an Autofire Area
at one point lands as many times as the roll allows.

The fighters are `shaped.armed`: OCV 9, DCV 5, ED 4, CON 18, 40 STUN.
"""
from __future__ import annotations

from dataclasses import replace

from shaped import (                                    # tests/loop/shaped.py
    TEMPLATE, Dice, Picks, armed, encounter_on, payloads, scene_with,
    shaped_blast,
)
from kirby_combat.attack_shapes import offer_is_buildable
from kirby_combat.charges import spent_charges
from kirby_combat.endurance import end_cost
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.loop.run import _situation_for
from kirby_combat.power_modifiers import (
    AreaShape, AreaSpec, AreaTargeting, AutofireSpec, unbuilt_reasons,
)
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")
#: END is counted (the superheroic default does not, 6E1 p.132's option).
COUNTED = replace(TEMPLATE, manage_endurance=True, manage_endurance_npc=True)


def _gun(shots=5, dice=8, **fields):
    return shaped_blast("smg", dice, autofire=AutofireSpec(shots=shots, unbuilt=()),
                        **fields)


def _fight(power, positions=None, *, targets=("b",)):
    """Inside 8m, so no Range Modifier (6E2 p.38)."""
    positions = positions or {"a": (0, 0, 0), "b": (8, 0, 0)}
    people = [armed("a", power, side=VILLAINS, dex=30)]
    people += [armed(t, None, side=HEROES) for t in targets]
    return encounter_on(scene_with(positions), *people, template=COUNTED)


def _menu(enc, who="a"):
    return _situation_for(enc.sessions[0], who).menu


def _burst(enc, target="b"):
    return next(a for a in _menu(enc) if a.kind == "autofire" and a.target_id == target)


def _fire(enc, offer, roller):
    s = enc.sessions[0]
    return resolve_chosen(s, s.combatants["a"], offer, template=COUNTED, roller=roller)


# ── the menu ─────────────────────────────────────────────────────────────────

def test_an_autofire_power_is_offered_as_a_burst_and_as_one_shot():
    """6E1 p.329: "he can always choose to fire fewer shots (even just one
    shot)" --- the plain attack stays; the burst is its own offer at the
    power's five shots. And 6E2 p.77 bars it from Rapid Fire and Multiple
    Attack (no Rapid Autofire Skill), which offered it until now."""
    enc = _fight(_gun(), {"a": (0, 0, 0), "b": (6, 0, 0), "c": (8, 0, 0)},
                 targets=("b", "c"))
    menu = _menu(enc)
    kinds = {(a.kind, a.target_id) for a in menu}
    assert ("attack", "b") in kinds and ("autofire", "b") in kinds
    assert _burst(enc).action_id.endswith(":5")
    assert not [a for a in menu if a.kind in ("rapid_fire", "multiple_attack", "sweep")]


def test_the_burst_is_cut_to_the_charges_left():
    """6E1 p.329: Charges "for each shot". 3 Charges, one spent: two shots."""

    enc = _fight(_gun(charges=3))
    single = next(a for a in _menu(enc) if a.kind == "attack")
    spent = _fire(enc, single, Dice(face=2)).session
    assert spent_charges(spent, "a") == {"smg": 1}
    burst = next(a for a in _situation_for(spent, "a").menu if a.kind == "autofire")
    assert burst.action_id.endswith(":2")


# ── one target ───────────────────────────────────────────────────────────────

def test_a_burst_hits_once_plus_once_per_two_points():
    """Andarra's arithmetic (6E2 p.44) on OCV 9 v DCV 5: a 10 makes it by 5
    -> 3 hits of 5 shots. 8d6 of 2s is 16 STUN, 12 through ED 4, three
    times: 36 off his 40. Each shot is a separate attack for Stunned (6E2
    p.44): 12 < CON 18, so he is NOT Stunned, though 36 in one blow would
    have done it. (No Knockback here, so no landing damage muddies the sum.)"""
    from kirby_combat.statuses import stunned_or_recovering_for

    enc = _fight(_gun(no_knockback=True))
    out = _fire(enc, _burst(enc), Dice(face=2, queue=[[4, 3, 3]])).session
    (use,) = payloads(out, autofire_use=True)
    assert use["hits"] == 3 and use["shots_fired"] == 5 and use["margin"] == 5
    hits = [p for p in payloads(out, kind="autofire") if p.get("autofire_shot")]
    assert len(hits) == 3 and all(p["hit"] for p in hits)
    assert out.combatants["b"].state.current_stun == 40 - 3 * 12
    assert not stunned_or_recovering_for(out, "b")


def test_a_burst_pays_end_and_charges_for_every_shot_fired():
    """6E1 p.329: "A character must pay Endurance (or use up Charges) for each
    shot he takes" --- five shots fired, three hit, five paid."""
    gun = _gun()
    enc = _fight(gun)
    out = _fire(enc, _burst(enc), Dice(face=2, queue=[[4, 3, 3]])).session
    assert out.combatants["a"].state.current_end == 40 - 5 * end_cost(gun)
    charged = _fight(_gun(charges=30))
    out = _fire(charged, _burst(charged), Dice(face=2, queue=[[4, 3, 3]])).session
    assert spent_charges(out, "a") == {"smg": 5}


def test_a_missed_burst_hits_nothing_and_still_costs_every_shot():
    gun = _gun()
    enc = _fight(gun)
    out = _fire(enc, _burst(enc), Dice(face=6)).session      # 18 always misses
    (use,) = payloads(out, autofire_use=True)
    assert use["hit"] is False and use["hits"] == 0
    assert out.combatants["b"].state.current_stun == 40
    assert out.combatants["a"].state.current_end == 40 - 5 * end_cost(gun)


def test_a_burst_knocks_back_once_from_its_largest_hit():
    """6E1 p.329: Knockback from "the BODY of the largest attack and add +1
    BODY for each additional hit" --- one roll, on one row. Three hits of
    8 BODY: 8 + 2 = 10 BODY against 2d6 of 2s (4) = 6 -> 12m."""
    enc = _fight(_gun())
    out = _fire(enc, _burst(enc), Dice(face=2, queue=[[4, 3, 3]])).session
    hits = [p for p in payloads(out, kind="autofire") if p.get("autofire_shot")]
    thrown = [p for p in hits if p.get("knockback")]
    assert len(thrown) == 1, [p.get("knockback") for p in hits]
    assert thrown[0]["knockback"]["distance_m"] == (8 + 2 - 4) * 2


def test_a_burst_resolves_through_run_phase():
    """Seam: offered, chosen, resolved under raise."""
    enc = _fight(_gun())
    result = run_phase(enc, Picks(lambda a, _s: a.kind == "autofire"),
                       roller=Dice(face=2), on_unresolvable="raise")
    assert result.kind == "autofire"
    assert payloads(result.session, autofire_use=True)


# ── several targets ──────────────────────────────────────────────────────────

def test_a_spray_rolls_once_per_man_at_the_whole_lines_penalty():
    """Three men 2m apart: a 4m line, -2 OCV on every roll, three shots (one
    a man; the line has only two 2m areas). One hit each at most."""
    enc = _fight(_gun(), {"a": (0, 0, 0), "b": (4, 0, 0), "c": (6, 0, 0),
                          "d": (8, 0, 0)}, targets=("b", "c", "d"))
    spray = next(a for a in _menu(enc) if a.kind == "autofire_spray")
    assert spray.target_ids == ("b", "c", "d") and spray.action_id.endswith(":3")
    out = _fire(enc, spray, Dice(face=2)).session
    (use,) = payloads(out, autofire_use=True)
    assert use["line_penalty"] == -2 and use["shots_fired"] == 3
    rows = [p for p in payloads(out, kind="autofire_spray") if p.get("autofire_shot")]
    assert [p["target_id"] for p in rows] == ["b", "c", "d"]
    assert all(p["effective_ocv"] == 9 - 2 for p in rows)
    for who in ("b", "c", "d"):
        assert out.combatants[who].state.current_stun == 40 - 12


def test_a_spray_reaches_only_as_far_as_its_shots():
    """6E2 p.44: a 5-shot weapon "could affect a maximum of 10m". b to c is
    8m (four 2m areas); d, 4m more, would make it 12m: left out."""
    enc = _fight(_gun(), {"a": (0, 0, 0), "b": (4, 0, 0), "c": (12, 0, 0),
                          "d": (16, 0, 0)}, targets=("b", "c", "d"))
    spray = next(a for a in _menu(enc) if a.kind == "autofire_spray")
    assert spray.target_ids == ("b", "c")


def test_a_spray_resolves_through_run_phase():
    enc = _fight(_gun(), {"a": (0, 0, 0), "b": (6, 0, 0), "c": (8, 0, 0)},
                 targets=("b", "c"))
    result = run_phase(enc, Picks(lambda a, _s: a.kind == "autofire_spray"),
                       roller=Dice(face=2), on_unresolvable="raise")
    assert result.kind == "autofire_spray"


# ── an Autofire Area ─────────────────────────────────────────────────────────

def _area(size=2.0):
    return AreaSpec(shape=AreaShape.RADIUS, size_m=size,
                    targeting=AreaTargeting.STANDARD, explosion=False,
                    personal_immunity=False, width_m=2.0, height_m=2.0,
                    thin_cone=False, unbuilt=())


def test_an_autofire_area_lands_as_often_as_the_roll_allows():
    """6E2 p.45: "the Attack Roll determines how many shots hit the target.
    The rest are considered misses". OCV 9 against the point's DCV 3: a 10
    makes it by 7 -> 4 landings of 5; each a 4d6 Area use (8 STUN, 4
    through) on b and on c beside him. Five shots paid."""
    gun = _gun(dice=4, area=_area())
    enc = _fight(gun, {"a": (0, 0, 0), "b": (7, 0, 0), "c": (8, 0, 0)},
                 targets=("b", "c"))
    assert not unbuilt_reasons(gun)
    burst = _burst(enc)
    assert offer_is_buildable(enc.sessions[0], "a", burst)
    assert not [a for a in _menu(enc) if a.kind == "autofire_spray"]
    out = _fire(enc, burst, Dice(face=2, queue=[[4, 3, 3]])).session
    assert len(payloads(out, area_use=True)) == 4
    for who in ("b", "c"):
        assert out.combatants[who].state.current_stun == 40 - 4 * 4
    assert out.combatants["a"].state.current_end == 40 - 5 * end_cost(gun)


def test_an_autofire_constant_attack_is_not_offered():
    """6E2 p.44: a Constant Autofire keeps hitting "with the same number of
    shots that hit him the first time"; nothing here maintains a count."""
    gun = _gun(constant=True)
    assert unbuilt_reasons(gun)
    enc = _fight(gun)
    s = enc.sessions[0]
    assert not [a for a in _menu(enc) if offer_is_buildable(s, "a", a)
                and a.kind == "autofire"]


def test_the_build_reads_the_shot_count():
    """HD's TWO / THREE / FIVE, and FIVE's DOUBLE adder (LVLPOWER 2): x2 per
    level (6E1 p.329: "up to double this 5 shot maximum for each additional
    +1/2")."""
    from dataclasses import dataclass, field

    from kirby_combat.power_modifiers import autofire_of

    @dataclass
    class _Mod:
        xmlid: str
        levels: float = 0
        option_id: str | None = None
        assigned_adders: list = field(default_factory=list)
        assigned_modifiers: list = field(default_factory=list)

    @dataclass
    class _P:
        assigned_modifiers: list
        xmlid: str = "RKA"
        sub_powers: list = field(default_factory=list)

    def shots(*mods):
        return autofire_of(_P(list(mods))).shots

    assert shots(_Mod("AUTOFIRE", option_id="THREE")) == 3
    assert shots(_Mod("AUTOFIRE", option_id="FIVE",
                      assigned_adders=[_Mod("DOUBLE", levels=1)])) == 10
    assert shots(_Mod("AUTOFIRE", option_id="FIVE",
                      assigned_adders=[_Mod("DOUBLE", levels=2)])) == 20
    assert autofire_of(_P([])) is None
