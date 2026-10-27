"""Enraged and Berserk roll, bite and recover (6E1 p.424-425).

On origin/main a character's Enraged/Berserk complication was read only by
tactics (`bait_enraged`); it never rolled and never changed what he could
do. Ported from the parked consumer's driver, with its three errors
corrected (see `kirby_combat/rage.py`).

The complications here are stubs shaped like kirby-cost's `Enraged`
(``xmlid``, ``input``, ``id``, ``assigned_adders`` with ``option_id``) ---
stated as data, so the test runs everywhere. Ogre (CV3: "Berserk in combat,
go 11-, recover 14-") reads through the same function from a real build.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conftest import blast                       # tests/loop/conftest.py
from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.encounter import Encounter
from kirby_combat.loop.run import run_phase
from kirby_combat.rage import (
    Circumstance, DEFENSIVE_KINDS, classify, rage_complications_of, rage_state,
)
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, RageRolled, VitalsChanged, make_author_combatant,
    make_author_engine,
)
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


class Dice:
    """Every die the same face."""

    def __init__(self, face: int) -> None:
        self.face = face

    def roll_dice(self, n: int) -> list[int]:
        return [self.face] * n


def _enraged(text: str, *, go: str = "14-", recover: str = "8-", berserk=False):
    adders = [SimpleNamespace(xmlid="CHANCETOGO", option_id=go),
              SimpleNamespace(xmlid="CHANCETORECOVER", option_id=recover),
              SimpleNamespace(xmlid="CIRCUMSTANCES", option_id="COMMON")]
    if berserk:
        adders.append(SimpleNamespace(xmlid="BERSERK", option_id=None))
    return SimpleNamespace(xmlid="ENRAGED", input=text, id=f"rage-{text}",
                           assigned_adders=adders)


def _man(id: str, side: str, *, dex: int = 20, stun: int = 40, end: int = 40,
         complications=()):
    man = synthetic_combatant(
        id=id, name=id, ocv=9, dcv=6, omcv=5, dmcv=5,
        spd=4, dex=dex, ego=15, str_=15, con=18, pre=15, rec=6,
        pd=4, ed=4, rpd=2, red=2, md=3, power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=stun, current_body=12, current_end=end,
        side=Side.named(side), attacks=[blast(f"{id}-eb")],
    )
    man.hero.complications = list(complications)
    return man


def _encounter(*men, segment: int = 12) -> Encounter:
    session = CombatSession.create(
        id="s", combatants=list(men), scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=1),
    ).start()
    return Encounter(id="e", turn=1, segment=segment, sessions=[session])


class Picks:
    def __init__(self, *kinds):
        self.kinds = kinds
        self.menus = []

    def choose(self, situation):
        # Out of turn (an Abort, a Held Action: `loop/reactions.py`) is not
        # his Phase menu: decline, and do not record it.
        if situation.out_of_turn is not None:
            return situation.menu[0].action_id
        self.menus.append((situation.actor.id, list(situation.menu)))
        for kind in self.kinds:
            for offer in situation.menu:
                if offer.kind == kind:
                    return offer.action_id
        return situation.ordered_menu[0].action_id


def _rolls(session, who):
    return [e for e in session.event_log
            if e.kind == "RageRolled" and e.combatant_id == who]


# ---- reading the circumstance --------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("in combat", {Circumstance.IN_COMBAT}),
    ("in combat or when injured", {Circumstance.IN_COMBAT, Circumstance.TAKES_BODY}),
    ("if takes BODY damage in combat", {Circumstance.TAKES_BODY}),
    ("if wounded (takeds BODY)", {Circumstance.TAKES_BODY}),
    ("if injured or harmed", {Circumstance.TAKES_BODY}),
    ("when he sees his own blood", {Circumstance.TAKES_BODY}),
    ("if challeneged or attacked", {Circumstance.ATTACKED}),
    ("when hit", {Circumstance.ATTACKED}),
    # Not his own condition, a special effect, or social: the GM's call.
    ("if sister Knocled Out or seriously hurt", set()),
    ("when sibling takes BODY", set()),
    ("if hit by electricity", set()),
    ("when attacked from behind or by surprise", set()),
    ("if insulted", set()),
    ("when smells blood", set()),
])
def test_only_what_the_fight_can_see_is_read(text, expected):
    assert classify(text) == frozenset(expected)


def test_a_sheet_without_its_rolls_is_not_run():
    """The driver guessed 11- for a missing roll; inventing the character."""
    rage = _enraged("in combat")
    rage.assigned_adders = [a for a in rage.assigned_adders if a.xmlid != "CHANCETOGO"]
    assert rage_complications_of(_man("ogre", "v", complications=[rage])) == []


def test_berserk_is_read_from_its_adder():
    [rage] = rage_complications_of(_man("ogre", "v", complications=[
        _enraged("in combat", go="11-", recover="14-", berserk=True)]))
    assert (rage.berserk, rage.go, rage.recover) == (True, 11, 14)


# ---- going -----------------------------------------------------------------------

def test_berserk_in_combat_goes_and_attacks_the_nearest_friend_or_foe():
    """6E1 p.425: Berserk "can't tell friend from foe" and attacks whoever
    is nearest. With no map to measure, the roster's order decides (ruling):
    his own teammate stands first."""
    ogre = _man("ogre", "v", dex=30, complications=[
        _enraged("in combat", go="11-", recover="14-", berserk=True)])
    enc = _encounter(_man("henchman", "v"), ogre, _man("hero", "h"))
    chooser = Picks("dodge", "attack")
    # Ogre (DEX 30) acts first. A roll of 3 (all ones) is under 11-.
    result = run_phase(enc, chooser, roller=Dice(1), on_unresolvable="raise")
    assert result.actor_id == "ogre"
    [go] = _rolls(result.session, "ogre")
    assert (go.roll_kind, go.succeeded, go.target_id) == ("go", True, "henchman")
    menu = chooser.menus[-1][1]
    assert {a.target_id for a in menu if a.target_id} == {"henchman"}
    assert not [a for a in menu if a.kind in DEFENSIVE_KINDS]
    assert result.kind == "attack", "no Dodge to take, so he attacks"


def test_he_rolls_every_phase_until_he_goes():
    """6E1 p.424: "Every Phase a character is in a situation where he can
    become Enraged, he should roll"; a miss leaves him in control."""
    ogre = _man("ogre", "v", dex=30, complications=[_enraged("in combat", go="8-")])
    enc = _encounter(ogre, _man("hero", "h"))
    chooser = Picks("dodge")
    result = run_phase(enc, chooser, roller=Dice(6), on_unresolvable="raise")
    [go] = _rolls(result.session, "ogre")
    assert not go.succeeded
    assert not rage_state(result.session, "ogre").raging
    assert result.kind == "dodge", "in control, he may still defend"


def test_an_insult_rage_does_not_go_off_when_he_is_shot():
    """The driver's error: it rolled on any BODY taken, whatever the sheet."""
    ogre = _man("ogre", "v", dex=30, complications=[_enraged("if insulted")])
    enc = _encounter(ogre, _man("hero", "h"))
    session = _wounded(enc.sessions[0], "ogre", by="hero")
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    result = run_phase(enc, Picks("attack"), roller=Dice(1), on_unresolvable="raise")
    assert _rolls(result.session, "ogre") == []


def _wounded(session, who, *, by):
    now = session.event_log[-1].timestamp
    session = apply_event(session, ActionDeclared(
        id="shot", session_id=session.id, sequence=len(session.event_log) + 1,
        timestamp=now, author=make_author_combatant(by), combatant_id=by,
        action_type="attack", targets=[who], parameters={},
    ))
    return apply_event(session, VitalsChanged(
        id="wound", session_id=session.id, sequence=len(session.event_log) + 1,
        timestamp=now, author=make_author_engine(), combatant_id=who,
        stun=-8, body=-3, reason="damage",
    ))


def test_a_wound_enrages_him_at_the_man_who_did_it():
    ogre = _man("ogre", "v", dex=30, complications=[_enraged("if takes BODY")])
    enc = _encounter(ogre, _man("bystander", "h"), _man("shooter", "h"))
    session = _wounded(enc.sessions[0], "ogre", by="shooter")
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    chooser = Picks("attack")
    result = run_phase(enc, chooser, roller=Dice(1), on_unresolvable="raise")
    [go] = _rolls(result.session, "ogre")
    assert (go.succeeded, go.target_id, go.reason) == (True, "shooter", "takes_body")
    assert {a.target_id for a in chooser.menus[-1][1] if a.target_id} == {"shooter"}


# ---- recovering ----------------------------------------------------------------

def _raging(session, who, target, *, berserk=False):
    return apply_event(session, RageRolled(
        id="went", session_id=session.id, sequence=len(session.event_log) + 1,
        timestamp=session.event_log[-1].timestamp, author=make_author_engine(),
        combatant_id=who, complication_id="rage-in combat", roll_kind="go",
        roll=3, target_number=14, succeeded=True, berserk=berserk,
        target_id=target, reason="in_combat", turn=1, segment=12,
    ))


def test_he_rolls_to_recover_when_his_target_is_down():
    """6E1 p.424: "Once an Enraged individual finishes with his target, he
    must roll his chance of recovery." A made roll ends it."""
    ogre = _man("ogre", "v", dex=30, complications=[_enraged("in combat", recover="8-")])
    enc = _encounter(ogre, _man("down", "h", stun=0), _man("hero", "h"))
    enc = Encounter(id="e", turn=1, segment=12,
                    sessions=[_raging(enc.sessions[0], "ogre", "down")])
    result = run_phase(enc, Picks("dodge"), roller=Dice(1), on_unresolvable="raise")
    recover = [e for e in _rolls(result.session, "ogre") if e.roll_kind == "recover"]
    assert [(e.reason, e.succeeded) for e in recover] == [("target_down", True)]
    assert not rage_state(result.session, "ogre").raging
    assert result.kind == "dodge", "calm again, he may defend"


def test_failing_it_he_turns_on_the_next_of_his_targets_side():
    ogre = _man("ogre", "v", dex=30, complications=[_enraged("in combat", recover="8-")])
    enc = _encounter(_man("mate", "v"), ogre, _man("down", "h", stun=0),
                     _man("hero", "h"))
    enc = Encounter(id="e", turn=1, segment=12,
                    sessions=[_raging(enc.sessions[0], "ogre", "down")])
    chooser = Picks("attack")
    result = run_phase(enc, chooser, roller=Dice(6), on_unresolvable="raise")
    assert rage_state(result.session, "ogre").target_id == "hero"
    assert "RageTargeted" in [e.kind for e in result.events]
    assert {a.target_id for a in chooser.menus[-1][1] if a.target_id} == {"hero"}


def test_out_of_end_he_rolls_to_recover():
    ogre = _man("ogre", "v", dex=30, end=0,
                complications=[_enraged("in combat", recover="8-")])
    enc = _encounter(ogre, _man("hero", "h"))
    enc = Encounter(id="e", turn=1, segment=12,
                    sessions=[_raging(enc.sessions[0], "ogre", "hero")])
    result = run_phase(enc, Picks("attack"), roller=Dice(6), on_unresolvable="raise")
    recover = [e for e in _rolls(result.session, "ogre") if e.roll_kind == "recover"]
    assert [(e.reason, e.succeeded) for e in recover] == [("out_of_end", False)]


def test_he_does_not_roll_to_recover_every_phase():
    """The driver's error: a roll every Phase. Target standing, END left."""
    ogre = _man("ogre", "v", dex=30, complications=[_enraged("in combat")])
    enc = _encounter(ogre, _man("hero", "h"))
    enc = Encounter(id="e", turn=1, segment=12,
                    sessions=[_raging(enc.sessions[0], "ogre", "hero")])
    result = run_phase(enc, Picks("attack"), roller=Dice(6), on_unresolvable="raise")
    assert [e.roll_kind for e in _rolls(result.session, "ogre")] == ["go"]


def test_post_segment_12_gives_him_a_free_attempt():
    """6E1 p.424: "a free attempt to recover from being Enraged in
    Post-Segment 12 if he hasn't attempted to recover in that Turn"."""
    ogre = _man("ogre", "v", dex=30, complications=[_enraged("in combat", recover="8-")])
    enc = _encounter(ogre, _man("hero", "h"))
    enc = Encounter(id="e", turn=1, segment=12,
                    sessions=[_raging(enc.sessions[0], "ogre", "hero")])
    chooser = Picks("attack")
    for _ in range(3):                      # ogre, hero, then into Turn 2
        result = run_phase(enc, chooser, roller=Dice(6), on_unresolvable="raise")
        enc = result.encounter
    log = enc.sessions[0].event_log
    free = [i for i, e in enumerate(log) if e.kind == "RageRolled"
            and e.roll_kind == "recover" and e.reason == "post_segment_12"]
    wrap = [i for i, e in enumerate(log) if e.kind == "SegmentAdvanced"
            and e.to_turn == 2]
    assert free and wrap and free[0] < wrap[0]
    assert len(free) == 1
