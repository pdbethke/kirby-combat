"""Mental Illusions that change what the victim does (6E1 p.250-253).

Until now a Mental Illusion made its MCV Attack Roll, rolled its dice, wrote
a degree into the log and changed nothing: no illusion was named, nothing was
established, nobody made a Breakout Roll, and the victim fought on exactly as
before. RAW (6E1 p.250) the mentalist "defines the illusion he wants the
target to perceive, and the GM determines what level of effect he needs" ---
so, like Mind Control's order, the illusion is chosen BEFORE the roll, a
short roll "has no effect", and an established one lasts "until he succeeds
with a Breakout Roll".

Every test drives the engine's own doors: `enumerate_actions`,
`resolve_chosen`, `roll_breakouts` and `run_phase`.
"""
from __future__ import annotations

from dataclasses import replace

from conftest import fighter                          # noqa: F401  (loop fixtures on path)
from test_mental_combat_bites import (
    TEMPLATE, _Dice, _Power, _Records, _brainchild, _fight, _offer, _person, _targets,
)

from kirby_combat.cv_modifiers import effective_dcv_for
from kirby_combat.encounter import Encounter
from kirby_combat.enumeration import enumerate_actions
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import resolve_chosen
from kirby_combat.mental.continuing import effects_on, roll_breakouts
from kirby_combat.mental.mental_illusion import ILLUSIONS, illusion_named
from kirby_dice import RandomRoller


def _illusionist(levels: int = 12, active_cost: int = 60):
    psi = _brainchild()
    power = _Power("MENTALILLUSION", levels)
    power.active_cost = active_cost
    psi.hero.powers.append(power)
    return psi, power


def _illusion(name: str, *, extra=(), effect: int = 6, levels: int = 12,
              active_cost: int = 60, md: int = 0):
    """psi casts ``name`` at mark; the MCV roll hits, the dice all show ``effect``."""
    psi, power = _illusionist(levels, active_cost)
    mark = _person("mark", "gang", dex=30, md=md)
    session = _fight(psi, mark, *extra)
    resolved = resolve_chosen(session, session.combatants["psi"],
                              _offer("mental_illusion", "mark", power, order=name),
                              template=TEMPLATE, roller=_Dice((1, 1, 1), effect=effect))
    return resolved.session, resolved.session.event_log[-1].result_payload


def _marks_phase(session, roll):
    session = roll_breakouts(session, "mark", _Dice(roll, effect=2))
    chooser = _Records()
    result = run_phase(Encounter(id="e", turn=1, segment=12, sessions=[session]),
                       chooser, roller=RandomRoller(seed=21))
    assert result.actor_id == "mark"
    return result, chooser.menu


# ── the offers ──────────────────────────────────────────────────────────────

def test_each_illusion_is_its_own_offer_naming_the_total_it_needs():
    psi, _ = _illusionist()
    mark = _person("mark", "gang", dex=30, md=3)
    pal = _person("pal", "gang", dex=20)
    menu = [a for a in enumerate_actions(psi, [mark, pal])
            if a.kind == "mental_illusion" and a.target_id == "mark"]
    assert {a.order for a in menu} == {i.name for i in ILLUSIONS}
    vanish = next(a for a in menu if a.order == "vanish")
    assert "23" in vanish.summary          # EGO 10 + 10 + Mental Defense 3


def test_friends_as_foes_needs_friends():
    psi, _ = _illusionist()
    menu = enumerate_actions(psi, [_person("mark", "gang", dex=30)])
    assert "friends_as_foes" not in {a.order for a in menu if a.kind == "mental_illusion"}


def test_an_illusion_that_can_hurt_is_not_offered_from_a_power_with_no_active_points():
    """6E1 p.253 caps an illusory attack at the power's Active Points; a
    power that states none cannot be priced, so it is not offered to hurt."""
    psi, _ = _illusionist(active_cost=0)
    orders = {a.order for a in enumerate_actions(psi, [_person("mark", "gang", dex=30)])
              if a.kind == "mental_illusion"}
    assert not orders & {"phantom_attack", "phantom_wound"}
    assert "vanish" in orders


# ── establishing it ─────────────────────────────────────────────────────────

def test_a_short_effect_roll_has_no_effect():
    """6E1 p.250: "If the Effect Roll is not sufficient to reach the desired
    level, the attack has no effect". 12 ones = 12 vs EGO 10 + 30."""
    session, payload = _illusion("lost_in_illusion", effect=1)
    assert payload["established"] is False and payload["required_total"] == 40
    assert effects_on(session, "mark") == []


def test_mental_defense_comes_off_before_the_table():
    session, payload = _illusion("vanish", effect=1, md=5)
    assert (payload["effect_rolled"], payload["effect_total"]) == (12, 7)


def test_an_established_illusion_is_a_continuing_effect_with_a_breakout_roll():
    """72 against vanish's 10 + 10 = 20: 52 over, -10 to break out (6E1 p.152)."""
    session, payload = _illusion("vanish")
    assert payload["established"] is True
    (effect,) = effects_on(session, "mark")
    assert (effect.kind, effect.illusion, effect.breakout_modifier) == (
        "mental_illusion", "vanish", -10)


# ── what he does once he believes it ────────────────────────────────────────

def test_vanish_takes_the_illusionist_off_his_list():
    session, _ = _illusion("vanish", extra=[_person("rando", "solo", dex=20)])
    _, menu = _marks_phase(session, (6, 6, 6))
    assert "psi" not in _targets(menu) and "rando" in _targets(menu)


def test_seeing_through_it_ends_it():
    session, _ = _illusion("vanish")
    result, menu = _marks_phase(session, (1, 1, 1))
    assert "psi" in _targets(menu)
    assert effects_on(result.session, "mark") == []


def test_friends_as_foes_puts_his_friends_on_his_list():
    """6E1 p.250, a major change: "making friends look and act like enemies"."""
    session, _ = _illusion("friends_as_foes", extra=[_person("pal", "gang", dex=20)])
    _, menu = _marks_phase(session, (6, 6, 6))
    assert {"pal", "psi"} <= _targets(menu)


def test_a_peaceful_meadow_has_nobody_in_it_to_attack():
    """6E1 p.250, completely altering the setting: "a battlefield appears to
    be a peaceful meadow"."""
    session, _ = _illusion("peaceful_meadow", extra=[_person("rando", "solo", dex=20)])
    _, menu = _marks_phase(session, (6, 6, 6))
    assert not _targets(menu) & {"psi", "rando"}


def test_lost_in_the_illusion_he_stands_still_at_half_dcv():
    """6E1 p.251, EGO+30: "the victim no longer interacts with his
    environment ... in most situations he simply stands still. Characters in
    this state are usually at 1/2 DCV"."""
    session, _ = _illusion("lost_in_illusion")
    result, menu = _marks_phase(session, (6, 6, 6))
    assert menu == []
    spent = [e for e in result.events if e.kind == "PhaseSpent"]
    assert [e.reason for e in spent] == ["entranced"]
    assert effective_dcv_for(result.session, "mark") == 3          # 5 halved, rounded his way


def test_an_illusion_is_not_obeyed_before_the_first_breakout_roll():
    session, _ = _illusion("lost_in_illusion")
    assert effective_dcv_for(session, "mark") == 5


# ── harmful illusions (6E1 p.253) ───────────────────────────────────────────

def test_a_phantom_attack_hurts_only_after_the_first_failed_breakout_roll():
    """p.253: "Damage from Mental Illusions doesn't apply until after the
    target fails his first Breakout Roll." The cap is the lesser of the
    Effect Roll and the power's Active Points: min(48, 40) = 40 -> 8d6
    (the Storvak example: 40 points / 5 = 8d6). Eight 2s = 16 STUN, less
    ED 5 = 11. STUN only at +10."""
    session, payload = _illusion("phantom_attack", effect=6, levels=8, active_cost=40)
    assert payload["established"] is True and payload["illusion_dice"] == 8
    assert session.combatants["mark"].state.current_stun == 40
    after = roll_breakouts(session, "mark", _Dice((6, 6, 6), effect=2))
    mark = after.combatants["mark"].state
    assert (mark.current_stun, mark.current_body) == (40 - 11, 12)


def test_a_phantom_attack_seen_through_does_nothing():
    session, _ = _illusion("phantom_attack", levels=8, active_cost=40)
    after = roll_breakouts(session, "mark", _Dice((1, 1, 1), effect=2))
    assert after.combatants["mark"].state.current_stun == 40


def test_a_phantom_attack_strikes_once_not_every_phase():
    """p.253: "Illusory attacks should function like Instant Powers, doing
    damage once per Effect Roll"."""
    session, _ = _illusion("phantom_attack", levels=8, active_cost=40)
    once = roll_breakouts(session, "mark", _Dice((6, 6, 6), effect=2))
    a_turn_on = replace(once, timeline=replace(once.timeline, turn=once.timeline.turn + 1))
    later = roll_breakouts(a_turn_on, "mark", _Dice((6, 6, 6), effect=2))
    assert [e.broke_free for e in later.event_log if e.kind == "BreakoutRolled"] == [False, False]
    assert later.combatants["mark"].state.current_stun == once.combatants["mark"].state.current_stun


def test_a_phantom_wound_does_body_too():
    """+20 on the table: "Target takes BODY and STUN from illusory attacks".
    Eight 2s are 8 BODY of Normal Damage, less ED 5 = 3."""
    session, payload = _illusion("phantom_wound", effect=6, levels=8, active_cost=40)
    assert payload["required_total"] == 40
    after = roll_breakouts(session, "mark", _Dice((6, 6, 6), effect=2))
    mark = after.combatants["mark"].state
    assert (mark.current_stun, mark.current_body) == (40 - 11, 12 - 3)


def test_the_illusion_registry_cites_its_pages():
    assert all(i.page.startswith("6E1 p.") for i in ILLUSIONS)
    assert illusion_named("vanish").level == 10
