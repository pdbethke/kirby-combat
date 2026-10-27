"""A Phase in halves (6E2 p.20-26), and the rules that hang off it.

On origin/main the loop gave a man ONE action a Phase: standing up took the
Phase, nobody could step up and then choose his blow, a Casual STR roll cost
as much as a punch, and a break-out that the book says "takes no time at all"
(6E2 p.126) ended the Phase. Every test here drives `run_phase` with
``on_unresolvable="raise"``.
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from shaped import Dice, armed, encounter_on, scene_with      # tests/loop/shaped.py
from conftest import blast                                    # tests/loop/conftest.py
from kirby_combat.action_time import KIND_TIMES
from kirby_combat.actions.entangle import Entangle, Transparency
from kirby_combat.loop import run_phase
from kirby_combat.loop.registry import registered_kinds
from kirby_combat.power_modifiers import ConcentrationDCV, ConcentrationSpec
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import (
    ActionResolved, RageRolled, make_author_engine,
)
from kirby_combat.statuses import FELL
from kirby_combat.side import Side
from kirby_combat.statuses import PRONE, statuses_for  # noqa: F401

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


class Wants:
    """Takes the first offer of each wanted kind in turn on HIS Phase menus;
    declines every out-of-turn question; records the Phase menus."""

    def __init__(self, *wants):
        self.wants = list(wants)
        self.menus: list[tuple[str, list]] = []

    def choose(self, situation):
        if situation.out_of_turn is not None:
            return situation.menu[0].action_id
        self.menus.append((situation.actor.id, list(situation.menu)))
        if self.wants:
            want = self.wants.pop(0)
            for offer in situation.menu:
                if (want(offer) if callable(want) else offer.kind == want):
                    return offer.action_id
            raise AssertionError(f"{want!r} not offered: {[a.kind for a in situation.menu]}")
        return situation.menu[0].action_id


def _emit(encounter, event_cls, **fields):
    s = encounter.sessions[0]
    s = apply_event(s, event_cls(
        id=str(uuid.uuid4()), session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=datetime.now(timezone.utc), author=make_author_engine(), **fields))
    return replace(encounter, sessions=[s])


def _knocked_down(enc, who):
    """Down, the way a martial Target Falls writes it (`statuses.FELL`)."""
    return _emit(enc, ActionResolved, declaration_event_id="",
                 result_payload={"kind": "test_fall", FELL: [who]})


def _spent(session, who):
    return [e for e in session.event_log if e.kind == "PhaseSpent" and e.combatant_id == who]


def _two_men(a_power=None, *, b_power=None, distance=1.0, **a_stats):
    scene = scene_with({"a": (0, 0, 0), "b": (distance, 0, 0)})
    return encounter_on(scene,
                        armed("a", a_power or blast("a-eb", 4), side=VILLAINS, dex=30, **a_stats),
                        armed("b", b_power, side=HEROES, dex=10))


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

def test_every_kind_has_a_time():
    """No kind's time is a default: every registered kind is priced."""
    assert registered_kinds() <= set(KIND_TIMES), sorted(registered_kinds() - set(KIND_TIMES))


# ---------------------------------------------------------------------------
# Two Half Phase Actions, or a Half Phase Action and an attack
# ---------------------------------------------------------------------------

def test_standing_up_is_a_half_phase_and_he_can_still_attack():
    """6E2 p.25: "Get to one's feet: 1/2 Phase". He stands, and the same
    Phase comes back to him with an attack on offer and no Full Phase
    Action (a Recovery, 6E2 p.25)."""
    enc = _knocked_down(_two_men(), "a")
    chooser = Wants("stand_up", "attack")
    first = run_phase(enc, chooser, roller=Dice(face=3), on_unresolvable="raise")
    assert first.kind == "stand_up" and PRONE not in statuses_for(first.session, "a")
    assert _spent(first.session, "a") == []
    second = run_phase(first.encounter, chooser, roller=Dice(face=3), on_unresolvable="raise")
    assert second.actor_id == "a" and second.kind == "attack"
    kinds = {a.kind for a in chooser.menus[1][1]}
    assert "recover" not in kinds and "stand_up" not in kinds
    assert len(_spent(second.session, "a")) == 1


def test_a_half_move_then_the_blow_he_chooses():
    """6E2 p.26: a Half Move leaves "another Half Phase Action in that
    Phase". He walks up, and then the strike is on his menu from where he
    now stands."""
    scene_enc = _two_men(distance=6.0)
    chooser = Wants("half_move", "strike")
    first = run_phase(scene_enc, chooser, roller=Dice(face=3), on_unresolvable="raise")
    assert first.kind == "half_move" and _spent(first.session, "a") == []
    moved = first.session.scene.combatant_positions["a"]
    assert 0 < moved.x <= 6.0
    second = run_phase(first.encounter, chooser, roller=Dice(face=3), on_unresolvable="raise")
    assert second.actor_id == "a" and second.kind == "strike"
    second_kinds = {a.kind for a in chooser.menus[1][1]}
    assert not second_kinds & {"move", "move_strike", "recover", "set"}


def test_two_half_moves_and_the_phase_is_gone():
    chooser = Wants("half_move", "half_move")
    enc = _two_men(distance=30.0)
    first = run_phase(enc, chooser, roller=Dice(face=3), on_unresolvable="raise")
    second = run_phase(first.encounter, chooser, roller=Dice(face=3), on_unresolvable="raise")
    assert second.actor_id == "a" and len(_spent(second.session, "a")) == 1


def test_an_attack_ends_the_phase():
    chooser = Wants("attack")
    out = run_phase(_two_men(), chooser, roller=Dice(face=3), on_unresolvable="raise")
    assert len(_spent(out.session, "a")) == 1


def test_a_very_impressed_man_gets_one_half_phase():
    """6E2 p.139 (PRE+10): he "only performs a Half Phase Action during his
    next Phase" --- the same fold that gives everyone else two."""
    from kirby_combat.session.events import PresenceApplied

    # Shouted at by a man no longer here, so there is nobody to hesitate
    # behind (the impressed half of the tier, `can_yield_to`).
    enc = _emit(_two_men(), PresenceApplied, target_id="a", attacker_id="gone",
                tier="very_impressed", segments=12)
    enc = _knocked_down(enc, "a")
    chooser = Wants("stand_up")
    out = run_phase(enc, chooser, roller=Dice(face=3), on_unresolvable="raise")
    assert out.kind == "stand_up" and len(_spent(out.session, "a")) == 1


def test_a_held_half_phase_is_used_as_one():
    """6E2 p.22: "A character may perform a Half Phase Action and then Hold a
    Half Phase". Released before b's Phase, its menu has no Full Phase
    Action."""
    enc = _two_men(distance=30.0)
    chooser = Wants("half_move", "hold")
    first = run_phase(enc, chooser, roller=Dice(face=3), on_unresolvable="raise")
    second = run_phase(first.encounter, chooser, roller=Dice(face=3), on_unresolvable="raise")
    assert second.kind == "hold"

    seen = []

    class Holder:
        def choose(self, situation):
            if situation.out_of_turn is not None and situation.actor.id == "a":
                seen.append({a.kind for a in situation.menu})
            return situation.menu[0].action_id

    run_phase(second.encounter, Holder(), roller=Dice(face=3), on_unresolvable="raise")
    assert seen and not seen[0] & {"move", "recover", "set", "move_strike"}
    assert "half_move" in seen[0]


# ---------------------------------------------------------------------------
# Entangles and Grabs: Casual STR, the break-out tiers, END
# ---------------------------------------------------------------------------

def _entangled(enc, *, body=4, pd=0, transparency=Transparency.NONE):
    s = enc.sessions[0]
    s, _ = Entangle.apply(s, attacker_id="b", target_id="a", entangle_body=body,
                          entangle_pd=pd, entangle_ed=pd, transparency=transparency,
                          both_take_damage=False)
    return replace(enc, sessions=[s])


def test_casual_str_takes_no_time_once_a_segment():
    """6E2 p.25: "Use STR or a power Casually: 0 Phase"; 6E1 p.134: once per
    Segment. Shrugging fails (1s), the Phase is still his, and the Casual
    offer is gone."""
    enc = _entangled(_two_men(), body=8)
    chooser = Wants(lambda a: a.action_id == "escape:str_casual", "escape_str")
    first = run_phase(enc, chooser, roller=Dice(face=1), on_unresolvable="raise")
    assert first.kind == "escape_str" and _spent(first.session, "a") == []
    ids = {a.action_id for a in chooser.menus[0][1]}
    assert "escape:str_casual" in ids
    run_phase(first.encounter, chooser, roller=Dice(face=1), on_unresolvable="raise")
    assert "escape:str_casual" not in {a.action_id for a in chooser.menus[1][1]}


@pytest.mark.parametrize("face, body, spent, left", [
    (6, 3, 0, 2),       # STR 15 = 3d6 of 6s = 6 BODY >= twice 3: no time at all
    (6, 6, 0, 1),       # 6 BODY >= 6: free, one Half Phase to act
    (6, 7, 1, None),    # 6 < 7: still held, no more Actions that Phase
])
def test_the_break_out_tiers(face, body, spent, left):
    """6E2 p.126, for an Entangle with no DEF."""
    from kirby_combat.action_time import halves_left

    enc = _entangled(_two_men(), body=body)
    chooser = Wants(lambda a: a.action_id == "escape:str_full")
    out = run_phase(enc, chooser, roller=Dice(face=face), on_unresolvable="raise")
    assert len(_spent(out.session, "a")) == spent
    if left is not None:
        assert halves_left(out.session, "a") == left
        nxt = Wants(lambda a: True)
        run_phase(out.encounter, nxt, roller=Dice(face=3), on_unresolvable="raise")
        assert nxt.menus[0][0] == "a"
        assert ("set" in {a.kind for a in nxt.menus[0][1]}) is (left == 2)


def test_escaping_costs_the_end_of_the_str_used():
    """6E1 p.43: 1 END per 10 STR used; a heroic template counts END."""
    from kirby_combat.template import RAW_HEROIC

    scene = scene_with({"a": (0, 0, 0), "b": (1, 0, 0)})
    enc = encounter_on(scene, armed("a", blast("a-eb", 4), side=VILLAINS, dex=30, str_=20),
                       armed("b", None, side=HEROES, dex=10), template=RAW_HEROIC)
    enc = _entangled(enc, body=20)
    out = run_phase(enc, Wants(lambda a: a.action_id == "escape:str_full"),
                    roller=Dice(face=1), on_unresolvable="raise")
    spends = [e.end for e in out.session.event_log
              if e.kind == "VitalsChanged" and e.combatant_id == "a" and e.reason == "end_spent"]
    assert spends == [-2]


def test_str_only_entangle_cannot_be_blasted_from_inside():
    """6E1 p.221, Takes No Damage +1: "he can only apply his STR"."""
    from kirby_combat.loop.run import _situation_for

    open_ = _entangled(_two_men())
    sealed = _entangled(_two_men(), transparency=Transparency.STR_ONLY)
    limited = _entangled(_two_men(), transparency=Transparency.LIMITED)
    kinds = lambda e: {a.kind for a in _situation_for(e.sessions[0], "a").menu}
    assert "escape_attack" in kinds(open_)
    assert "escape_attack" in kinds(limited)
    assert "escape_attack" not in kinds(sealed)


def test_a_friend_can_shoot_the_entangle_off_him():
    """6E1 p.218: target the Entangle "at -3 OCV", "DCV 0", without
    damaging the man inside. OCV 9 - 3 against DCV 0 needs 17-; 4d6 of 5s
    is 4 BODY, 2 through its DEF 2, enough for a 2 BODY Entangle."""
    scene = scene_with({"a": (0, 0, 0), "c": (5, 0, 0), "b": (20, 0, 0)})
    enc = encounter_on(scene,
                       armed("a", blast("a-eb", 4), side=VILLAINS, dex=30),
                       armed("c", None, side=VILLAINS, dex=5),
                       armed("b", None, side=HEROES, dex=10))
    s = enc.sessions[0]
    s, _ = Entangle.apply(s, attacker_id="b", target_id="c", entangle_body=2,
                          entangle_pd=2, entangle_ed=2, transparency=Transparency.NONE,
                          both_take_damage=False)
    enc = replace(enc, sessions=[s])
    chooser = Wants("attack_entangle")
    out = run_phase(enc, chooser, roller=Dice(face=5), on_unresolvable="raise")
    assert out.kind == "attack_entangle"
    assert Entangle.held(out.session, "c", mental_paralysis=False) is None
    assert out.session.combatants["c"].state.current_stun == 40
    row = [e.result_payload for e in out.session.event_log
           if e.kind == "ActionResolved" and (e.result_payload or {}).get("kind") == "attack_entangle"][0]
    assert row["target_dcv"] == 0 and row["effective_ocv"] == 9 - 3
    assert row["body_through"] == 4 - 2


def test_no_outside_attack_on_a_transparent_entangle():
    """+1/4, +1/2: the overflow onto the man inside is not built; +1: no
    outside attack at all (6E1 p.221)."""
    from kirby_combat.loop.run import _situation_for

    for t in (Transparency.LIMITED, Transparency.ALL, Transparency.STR_ONLY):
        scene = scene_with({"a": (0, 0, 0), "c": (5, 0, 0), "b": (20, 0, 0)})
        enc = encounter_on(scene, armed("a", blast("a-eb", 4), side=VILLAINS, dex=30),
                           armed("c", None, side=VILLAINS, dex=5),
                           armed("b", None, side=HEROES, dex=10))
        s, _ = Entangle.apply(enc.sessions[0], attacker_id="b", target_id="c",
                              entangle_body=5, entangle_pd=2, entangle_ed=2,
                              transparency=t, both_take_damage=False)
        assert "attack_entangle" not in {a.kind for a in _situation_for(s, "a").menu}


def test_a_mental_paralysis_shields_his_mind():
    """6E1 p.219: its Mental Defense "also protects the Entangled character
    if anyone tries to attack him mentally". A 6d6 Mental Blast of 5s = 30
    STUN, less his MD 3 and the paralysis's MD 5."""
    from test_mental_combat_bites import _mental_blast

    psi = armed("a", _mental_blast(6), side=VILLAINS, dex=30, omcv=12)
    object.__setattr__(psi, "_explicit_is_mentalist", True)
    scene = scene_with({"a": (0, 0, 0), "b": (5, 0, 0)})
    enc = encounter_on(scene, psi, armed("b", None, side=HEROES, dex=10))
    s, _ = Entangle.apply_mental_paralysis(
        enc.sessions[0], attacker_id="a", target_id="b", entangle_body=3,
        entangle_md=5, transparency=Transparency.ALL)
    enc = replace(enc, sessions=[s])
    out = run_phase(enc, Wants("mental_blast"), roller=Dice(face=5), on_unresolvable="raise")
    assert out.session.combatants["b"].state.current_stun == 40 - (30 - 3 - 5)


# ---------------------------------------------------------------------------
# Concentration (6E1 p.374-375)
# ---------------------------------------------------------------------------

def _concentrating_blast(dcv=ConcentrationDCV.HALF):
    return replace(blast("a-focus", 4), concentration=ConcentrationSpec(
        dcv=dcv, oblivious=False, throughout=False, unbuilt=()))


def test_concentration_halves_his_dcv_until_his_next_phase():
    from kirby_combat.cv_modifiers import effective_dcv_for

    enc = _two_men(_concentrating_blast(), dcv=6)
    out = run_phase(enc, Wants("attack"), roller=Dice(face=3, queue=[[6, 6, 6]]),
                    on_unresolvable="raise")
    assert effective_dcv_for(out.session, "a") == 3
    zero = run_phase(_two_men(_concentrating_blast(ConcentrationDCV.ZERO), dcv=6),
                     Wants("attack"), roller=Dice(face=3, queue=[[6, 6, 6]]),
                     on_unresolvable="raise")
    assert effective_dcv_for(zero.session, "a") == 0


def test_a_concentrating_man_cannot_abort():
    """"nor may he Dodge" (6E1 p.374): b's attack in the same Segment finds
    nobody to ask."""
    from kirby_combat.loop.reactions import may_abort

    enc = _two_men(_concentrating_blast(), b_power=blast("b-eb", 4))
    out = run_phase(enc, Wants("attack"), roller=Dice(face=3, queue=[[6, 6, 6]]),
                    on_unresolvable="raise")
    assert not may_abort(out.session, "a", out.session.combatants["b"])


def test_damage_breaks_concentration():
    from kirby_combat.concentration import concentrating

    enc = _two_men(_concentrating_blast(), b_power=blast("b-eb", 4))
    out = run_phase(enc, Wants("attack"), roller=Dice(face=3, queue=[[6, 6, 6]]),
                    on_unresolvable="raise")
    assert concentrating(out.session, "a") is not None
    hit = run_phase(out.encounter, Wants("attack"), roller=Dice(face=3, queue=[[1, 1, 1]]),
                    on_unresolvable="raise")
    assert hit.actor_id == "b"
    assert concentrating(hit.session, "a") is None


def test_no_concentration_after_a_half_move():
    """"He may not move more than 2m per Phase" (6E1 p.374)."""
    chooser = Wants("half_move", lambda a: True)
    enc = _two_men(_concentrating_blast(), distance=10.0)
    first = run_phase(enc, chooser, roller=Dice(face=3), on_unresolvable="raise")
    run_phase(first.encounter, chooser, roller=Dice(face=3), on_unresolvable="raise")
    assert not [a for a in chooser.menus[1][1]
                if getattr(a._attack_view, "source_id", None) == "a-focus"]


# ---------------------------------------------------------------------------
# Rage (6E1 p.424-425)
# ---------------------------------------------------------------------------

def _enraged():
    adders = [SimpleNamespace(xmlid="CHANCETOGO", option_id="14-"),
              SimpleNamespace(xmlid="CHANCETORECOVER", option_id="8-")]
    return SimpleNamespace(xmlid="ENRAGED", input="in combat", id="rage-1",
                           assigned_adders=adders)


def _raging(enc, who, target):
    enc.sessions[0].combatants[who].hero.complications = [_enraged()]
    return _emit(enc, RageRolled, combatant_id=who, complication_id="rage-1",
                 roll_kind="go", roll=3, target_number=14, succeeded=True,
                 berserk=False, target_id=target, reason="in_combat", turn=1, segment=12)


def test_a_raging_man_neither_holds_nor_concentrates():
    from kirby_combat.loop.run import _situation_for

    enc = _raging(_two_men(_concentrating_blast(), also=(blast("a-eb", 4),)), "a", "b")
    menu = _situation_for(enc.sessions[0], "a").menu
    assert "hold" not in {a.kind for a in menu}
    assert not [a for a in menu if getattr(a._attack_view, "source_id", None) == "a-focus"]
    assert [a for a in menu if getattr(a._attack_view, "source_id", None) == "a-eb"]


def test_a_friend_can_snap_him_out_of_it():
    """6E1 p.424: "when someone attempts to snap him out of it". The friend
    spends a Half Phase; the raging man rolls 8- to recover (three 1s)."""
    from kirby_combat.rage import rage_state

    scene = scene_with({"a": (0, 0, 0), "c": (2, 0, 0), "b": (20, 0, 0)})
    enc = encounter_on(scene, armed("a", blast("a-eb", 4), side=VILLAINS, dex=30),
                       armed("c", None, side=VILLAINS, dex=5),
                       armed("b", None, side=HEROES, dex=10))
    enc = _raging(enc, "c", "b")
    out = run_phase(enc, Wants("snap_out_of_rage"), roller=Dice(face=1),
                    on_unresolvable="raise")
    assert out.kind == "snap_out_of_rage"
    assert not rage_state(out.session, "c").raging
    rolls = [e for e in out.session.event_log if e.kind == "RageRolled" and e.reason == "snapped_out"]
    assert len(rolls) == 1 and _spent(out.session, "a") == []


# ---------------------------------------------------------------------------
# Prone (6E2 p.129): already applied at the attack door
# ---------------------------------------------------------------------------

def test_a_prone_target_is_easier_to_hit():
    """6E2 p.129: "at half DCV when attacked by non-prone characters". At
    OCV 8 a roll of 15 misses a standing DCV 5 (11+8-5 = 14-) and hits a
    prone one (DCV 3: 16-)."""
    def landed(prone: bool):
        enc = _two_men(ocv=8)
        if prone:
            enc = _knocked_down(enc, "b")
        out = run_phase(enc, Wants("attack"), roller=Dice(face=5), on_unresolvable="raise")
        return out.session.combatants["b"].state.current_stun < 40
    assert not landed(False)
    assert landed(True)
