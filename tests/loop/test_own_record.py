"""His page says what his own last actions did (combat-decisions spec,
Phase 7's feedback).

Plague fired nine times at a dodging agent and missed every time, and made
group Presence Attacks that did nothing, and his page never said so.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from conftest import fighter                             # tests/loop/conftest.py
from kirby_dice import RandomRoller

from kirby_combat.loop.chooser import PhaseSituation
from kirby_combat.own_record import own_record_lines
from kirby_combat.session.apply import apply_event
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.session.events import ActionResolved, make_author_combatant
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate

TEMPLATE = CombatTemplate.default_6e_superheroic()


def _fight():
    return CombatSession.create(
        id="s", combatants=[fighter("plague", side=Side.named("v")),
                            fighter("agent", side=Side.named("h")),
                            fighter("agent2", side=Side.named("h"))],
        scene=None, template=TEMPLATE, dice_roller=RandomRoller(seed=1)).start()


def _did(session, actor, **payload):
    return apply_event(session, ActionResolved(
        id=str(uuid.uuid4()), session_id=session.id,
        sequence=len(session.event_log) + 1, timestamp=datetime.now(timezone.utc),
        author=make_author_combatant(actor), declaration_event_id="",
        result_payload=payload))


def _lines(session):
    return own_record_lines(PhaseSituation(
        actor=session.combatants["plague"], menu=[], session=session))


def test_nothing_before_he_has_acted():
    assert _lines(_fight()) == []


def test_his_misses_are_listed_and_the_run_is_said():
    s = _fight()
    for margin in (-7, -9, -5):
        s = _did(s, "plague", kind="attack", power_name="Incredibly Acute Disease",
                 target_id="agent", hit=False, margin=margin)
    lines = _lines(s)
    # A judged page (the default template) says it in words: no DCV given away.
    assert lines[:3] == ["Incredibly Acute Disease at agent: missed badly"] * 2 + [
        "Incredibly Acute Disease at agent: missed clearly"]
    assert lines[-1] == "you have missed agent 3 times running"


def test_a_hit_ends_the_run():
    s = _fight()
    s = _did(s, "plague", kind="attack", power_name="Blast", target_id="agent",
             hit=False, margin=-3)
    s = _did(s, "plague", kind="attack", power_name="Blast", target_id="agent",
             hit=True, margin=1, stun_dealt=12, body_dealt=3,
             status_changes=["Stunned"])
    lines = _lines(s)
    assert not any("times running" in x for x in lines)
    assert lines[-1].startswith("Blast at agent: hit; he staggered")


def test_a_presence_attack_that_did_nothing_says_so():
    s = _did(_fight(), "plague", kind="presence_attack_group",
             effects={"agent": "no_effect", "agent2": "no_effect"})
    assert _lines(s) == ["group Presence Attack on 2: no effect on any of them"]


def test_only_the_last_four_are_listed():
    s = _fight()
    for _ in range(6):
        s = _did(s, "plague", kind="attack", power_name="Blast", target_id="agent2",
                 hit=True, margin=2, stun_dealt=5, body_dealt=1, status_changes=[])
    lines = _lines(s)
    assert lines[0] == "(and 2 earlier)" and len(lines) == 5


def test_someone_elses_actions_are_not_his():
    s = _did(_fight(), "agent", kind="attack", power_name="Carbine",
             target_id="plague", hit=False, margin=-2)
    assert _lines(s) == []


def test_it_is_on_his_page():
    s = _did(_fight(), "plague", kind="attack", power_name="Blast",
             target_id="agent", hit=False, margin=-4)
    page = PhaseSituation(actor=s.combatants["plague"], menu=[], session=s).brief().render()
    assert "What your last actions did:" in page
