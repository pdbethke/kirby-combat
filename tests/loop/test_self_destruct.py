"""A Self Only damaging power is offered as `self_destruct`, as a last resort
(squad tactics spec, 7).

The Destroid's Self Destruct System (RKA 8d6, Self Only, 1 Charge which Never
Recovers) stays unbuilt as an ordinary attack (`test_self_only_is_not_an_attack`).
It is offered to a man who is Entangled or Grabbed (capture is imminent), or
who sits in a squad that is more than half down and makes an INT Roll at the
top of his Phase. The blast hurts only him. A Self Only Aid is not one.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from shaped import Dice, Picks, armed, encounter_on, scene_with, shaped_blast
from tests.corpus import require_template

from kirby_combat.actions.grab import Grab
from kirby_combat.charges import spent_charges
from kirby_combat.loop import run_phase
from kirby_combat.loop.run import _situation_for
from kirby_combat.self_destruct import (
    capture_is_imminent, judge_the_squad, squad_casualty_fraction,
)
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import VitalsChanged, make_author_engine
from kirby_combat.session.involvement import events_involving
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")
_PLACES = {"mark": (0, 0, 0), "bot": (1, 0, 0), "b": (20, 6, 0), "c": (20, -6, 0)}


def _bomb():
    """RKA 8d6, Self Only, no range: the Destroid's Self Destruct System."""
    return shaped_blast("sd", 8, name="Self Destruct System", xmlid="RKA",
                        damage_type="killing", defense_type="pd", range_m=0,
                        is_ranged=False, self_only=True)


def _one_charge(man, power_id="sd"):
    """Give ``man`` the build power behind his view, with 1 Charge."""
    charges = SimpleNamespace(xmlid="CHARGES", alias_for_vector="1", option_id="ONE")
    man.hero.powers.append(SimpleNamespace(
        id=power_id, xmlid="RKA", assigned_modifiers=[charges], sub_powers=[]))
    return man


def _cast(*, squad=None, int_=10, bomb=True, charged=True):
    bot = armed("bot", _bomb() if bomb else None, side=HEROES, squad=squad,
                int_=int_, dex=40)
    if bomb and charged:
        _one_charge(bot)
    people = [armed("mark", shaped_blast("gun", 4, range_m=100), side=VILLAINS),
              bot]
    for mate in ("b", "c"):
        people.append(armed(mate, shaped_blast("g", 4, range_m=100), side=HEROES,
                            squad=squad))
    return encounter_on(scene_with(_PLACES), *people)


def _kinds(session, who="bot"):
    return [a.kind for a in _situation_for(session, who).menu]


def _knock_out(session, cid):
    stun = session.combatants[cid].state.current_stun
    return apply_event(session, VitalsChanged(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=datetime.now(UTC),
        author=make_author_engine(), combatant_id=cid, stun=-stun, body=0, end=0))


def _grabbed(session):
    s, _ = Grab.declare_and_resolve(
        session, attacker_id="mark", target_id="bot", attacker_str=20,
        target_str=10, attacker_ocv=8, target_dcv=0, attack_roll=3)
    assert Grab.is_grabbed(s, "bot")[0]
    return s


def _lost_squad(squad="alpha"):
    s = _cast(squad=squad).sessions[0]
    return _knock_out(_knock_out(s, "b"), "c")


# ---- not in a fair fight ----

def test_not_offered_in_a_fair_fight():
    assert "self_destruct" not in _kinds(_cast(squad="alpha").sessions[0])


def test_it_is_still_not_an_ordinary_attack():
    assert "attack" not in _kinds(_grabbed(_cast().sessions[0]))


# ---- (a) capture is imminent ----

def test_offered_when_grabbed():
    s = _grabbed(_cast().sessions[0])
    assert capture_is_imminent(s, "bot")
    assert "self_destruct" in _kinds(s)


def test_offered_when_entangled(monkeypatch):
    from kirby_combat.actions.entangle import Entangle

    s = _cast().sessions[0]
    monkeypatch.setattr(Entangle, "is_entangled",
                        staticmethod(lambda session, cid: (cid == "bot", 5)))
    assert capture_is_imminent(s, "bot")
    assert "self_destruct" in _kinds(s)


def test_a_man_with_no_self_only_power_is_offered_nothing():
    s = _grabbed(_cast(bomb=False).sessions[0])
    assert "self_destruct" not in _kinds(s)


def test_a_used_up_charge_is_not_offered_again():
    enc = _cast()
    s = _grabbed(enc.sessions[0])
    result = run_phase(enc.__class__(**{**enc.__dict__, "sessions": [s]}),
                       Picks(lambda a, _s: a.kind == "self_destruct"),
                       roller=Dice(face=1), on_unresolvable="raise")
    assert result.kind == "self_destruct"
    after = result.encounter.sessions[0]
    assert spent_charges(after, "bot") == {"sd": 1}
    assert "self_destruct" not in _kinds(after)


# ---- (b) the squad is lost, and the INT Roll is made ----

def test_offered_when_the_squad_is_lost_and_int_roll_made():
    s = _lost_squad()
    assert squad_casualty_fraction(s, "bot") == pytest.approx(2 / 3)
    s = judge_the_squad(s, "bot", Dice(face=1))          # 3 <= 9 + 10/5
    (rolled,) = [e for e in s.event_log if e.kind == "SelfDestructRolled"]
    assert rolled.succeeded and rolled.roll == 3 and rolled.target_number == 11
    assert rolled.squad == "alpha" and rolled.side == "heroes"
    assert "self_destruct" in _kinds(s)


def test_not_offered_when_int_roll_failed():
    s = judge_the_squad(_lost_squad(), "bot", Dice(face=6))   # 18 > 11
    (rolled,) = [e for e in s.event_log if e.kind == "SelfDestructRolled"]
    assert not rolled.succeeded
    assert "self_destruct" not in _kinds(s)


def test_no_roll_is_made_while_the_squad_holds():
    enc = _cast(squad="alpha")
    s = _knock_out(enc.sessions[0], "b")                  # 1 of 3 is not above a half
    dice = Dice(face=1)
    s = judge_the_squad(s, "bot", dice)
    assert dice.calls == [] and "self_destruct" not in _kinds(s)


def test_one_roll_a_phase():
    s = _lost_squad()
    dice = Dice(face=6)
    s = judge_the_squad(judge_the_squad(s, "bot", dice), "bot", dice)
    assert dice.calls == [3]


def test_no_roll_without_a_use_left():
    s = _lost_squad()
    dice = Dice(face=1)
    s = judge_the_squad(_spend_the_charge(s), "bot", dice)
    assert dice.calls == []


def _spend_the_charge(session):
    from kirby_combat.session.events import ActionDeclared, ActionResolved, make_author_combatant

    declared = ActionDeclared(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=datetime.now(UTC),
        author=make_author_combatant("bot"), combatant_id="bot",
        action_type="self_destruct", targets=[], parameters={})
    s = apply_event(session, declared)
    return apply_event(s, ActionResolved(
        id=str(uuid.uuid4()), session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=datetime.now(UTC), author=make_author_combatant("bot"),
        declaration_event_id=declared.id, result_payload={"power_source_id": "sd"}))


def test_the_roll_is_made_at_the_top_of_his_own_phase():
    """Seam: run_phase rolls once, and the offer is on the menu he is handed."""
    enc = _cast(squad="alpha")
    s = _knock_out(_knock_out(enc.sessions[0], "b"), "c")
    enc = enc.__class__(**{**enc.__dict__, "sessions": [s]})
    pick = Picks(lambda a, _s: a.kind == "self_destruct")
    result = run_phase(enc, pick, roller=Dice(face=1), on_unresolvable="raise")
    assert result.actor_id == "bot"
    assert any(a.kind == "self_destruct" for a in pick.menus[0])
    rolled = [e for e in result.encounter.sessions[0].event_log
              if e.kind == "SelfDestructRolled"]
    assert len(rolled) == 1 and rolled[0].succeeded


def test_not_in_a_squad_only_capture_triggers():
    s = _knock_out(_knock_out(_cast(squad=None).sessions[0], "b"), "c")
    assert squad_casualty_fraction(s, "bot") is None
    dice = Dice(face=1)
    s = judge_the_squad(s, "bot", dice)
    assert dice.calls == [] and "self_destruct" not in _kinds(s)
    assert "self_destruct" in _kinds(_grabbed(s))


# ---- what it does ----

def test_the_blast_hurts_only_him():
    enc = _cast()
    s = _grabbed(enc.sessions[0])
    before = {c.id: (c.state.current_stun, c.state.current_body)
              for c in s.combatants.values()}
    result = run_phase(enc.__class__(**{**enc.__dict__, "sessions": [s]}),
                       Picks(lambda a, _s: a.kind == "self_destruct"),
                       roller=Dice(face=3), on_unresolvable="raise")
    after = result.encounter.sessions[0]
    now = {c.id: (c.state.current_stun, c.state.current_body)
           for c in after.combatants.values()}
    assert now["bot"] != before["bot"]
    assert {k: v for k, v in now.items() if k != "bot"} == \
        {k: v for k, v in before.items() if k != "bot"}     # mark is adjacent
    hurt = [e for e in after.event_log
            if e.kind == "VitalsChanged" and e.combatant_id == "bot"
            and e.caused_by == "bot" and e.body < 0]
    assert hurt
    assert any(e.kind == "ActionResolved" for e in events_involving(after, "bot"))


# ---- a Self Only Aid is not a self-destruct ----

def test_self_only_aid_is_untouched():
    require_template()
    from kirby_cost.io.build_json import build_from_json

    from kirby_combat.hero_view import HeroCombatant

    chars = [{"xmlid": x, "levels": 0} for x in (
        "STR", "DEX", "CON", "BODY", "STUN", "END", "SPD", "PD", "ED", "REC", "OCV", "DCV")]
    aid = {"id": "aid", "xmlid": "AID", "name": "Patch Up", "levels": 4,
           "input": "STR", "modifiers": [
               {"id": "so", "xmlid": "MODIFIER", "base_cost": -2.0, "alias": "Self Only"}]}
    build = build_from_json({
        "name": "Medic", "template": "Main6E", "base_points": 400,
        "disad_points": 75, "experience": 0, "characteristics": chars,
        "powers": [aid], "skills": [], "perks": [], "talents": [],
        "disadvantages": []})
    medic = HeroCombatant.from_build(build, id="medic")
    assert not [a for a in medic.attacks if getattr(a, "self_only", False)]
    from kirby_combat.self_destruct import self_destruct_offers

    s = _grabbed(_cast().sessions[0])
    assert self_destruct_offers(s, medic) == []


# ---- the narrowings that apply to every offer apply to this one ----

def test_a_man_ordered_to_withdraw_is_not_offered_it(monkeypatch):
    """Mind Control's withdraw cuts the menu to `WITHDRAW_KINDS` (6E1 p.256)."""
    from kirby_combat.loop import run
    from kirby_combat.mental.continuing import Obedience

    s = _grabbed(_cast().sessions[0])
    assert "self_destruct" in _kinds(s)
    monkeypatch.setattr(run, "obey", lambda session, actor, enemies, allies: Obedience(
        enemies=enemies, allies=allies, withdraw=True, entranced=False))
    assert "self_destruct" not in _kinds(s)


def test_a_raging_man_is_not_offered_it():
    """RULING (`rage.RageMenu.narrowed`): he fights only his rage target."""
    from kirby_combat.session.events import RageRolled

    s = _grabbed(_cast().sessions[0])
    assert "self_destruct" in _kinds(s)
    s = apply_event(s, RageRolled(
        id="went", session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=s.event_log[-1].timestamp, author=make_author_engine(),
        combatant_id="bot", complication_id="rage-in combat", roll_kind="go",
        roll=3, target_number=14, succeeded=True, berserk=False,
        target_id="mark", reason="in_combat", turn=1, segment=12))
    assert "self_destruct" not in _kinds(s)


def test_no_int_roll_when_capture_is_already_imminent():
    dice = Dice(face=1)
    s = judge_the_squad(_grabbed(_lost_squad()), "bot", dice)
    assert dice.calls == []


# ---- the blast records what it did to him ----

def _blast_him(dice_face, *, stun=40, bomb_dice=8):
    enc = _cast()
    s = _grabbed(enc.sessions[0])
    if bomb_dice != 8:
        s.combatants["bot"].attacks[0].damage_dice = bomb_dice
    result = run_phase(enc.__class__(**{**enc.__dict__, "sessions": [s]}),
                       Picks(lambda a, _s: a.kind == "self_destruct"),
                       roller=Dice(face=dice_face), on_unresolvable="raise")
    return result.encounter.sessions[0]


def test_a_lethal_self_blast_leaves_him_dead():
    from kirby_combat.statuses import DEAD, statuses_for

    after = _blast_him(6)                    # 8d6 killing, every die a 6
    assert after.combatants["bot"].state.current_body < 0
    assert DEAD in statuses_for(after, "bot")


def test_a_small_self_blast_stuns_him_without_killing_him():
    from kirby_combat.statuses import DEAD, STUNNED, statuses_for

    after = _blast_him(3, bomb_dice=4)       # 4d6 killing: more STUN than his CON 18, BODY short of death
    held = statuses_for(after, "bot")
    payload = [e.result_payload for e in after.event_log
               if e.kind == "ActionResolved"
               and (e.result_payload or {}).get("kind") == "self_destruct"][0]
    assert DEAD not in held
    assert ("Stunned" in payload["status_changes"]) == (STUNNED in held)
    assert payload["stun_dealt"] > 18 and STUNNED in held
    assert "Stunned" in payload["status_changes"]
