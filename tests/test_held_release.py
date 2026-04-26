"""Held Action release polish — match-on-event + release-with-resolution + expiry.

Per 6E2 p61 §HOLD AN ACTION.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from kirby_combat.actions.held_action import HeldAction
from kirby_combat.dice import FakeRoller
from kirby_combat.models import Combatant
from kirby_combat.session import CombatSession
from kirby_combat.session.events import (
    ActionDeclared, HeldActionDeclared, make_author_combatant,
)
from kirby_combat.template import CombatTemplate


def _session() -> CombatSession:
    a = Combatant(
        id="alice", name="alice", ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    b = Combatant(
        id="bob", name="bob", ocv=7, dcv=7, omcv=5, dmcv=5,
        spd=3, dex=15, ego=10, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )
    return CombatSession.create(
        id="s1", combatants=[a, b], scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def test_held_action_releases_on_exact_trigger_condition():
    """The match callback can compare event fields to the held trigger description."""
    s = _session()
    s, _ = HeldAction.declare(
        s, "alice",
        trigger_condition="when bob declares attack",
        for_action="strike",
    )

    # Bob declares an attack
    bob_attack = ActionDeclared(
        id=str(uuid.uuid4()), session_id="s1",
        sequence=len(s.event_log) + 1, timestamp=datetime.now(timezone.utc),
        author=make_author_combatant("bob"),
        combatant_id="bob", action_type="strike",
        targets=["alice"], parameters={},
    )
    from kirby_combat.session import apply_event
    s = apply_event(s, bob_attack)

    # Match callback: fire when bob declares any action
    def match(held: HeldActionDeclared, evt) -> bool:
        return (
            evt.kind == "ActionDeclared"
            and getattr(evt, "combatant_id", "") == "bob"
            and "bob" in held.trigger_condition
        )

    s, released = HeldAction.release_on_event(s, bob_attack, match=match)
    assert len(released) == 1
    assert HeldAction.get_pending(s, "alice") == []


def test_released_held_action_resolves_like_normal_action():
    """release_with_resolution emits ActionDeclared + ActionResolved for the holder."""
    s = _session()
    s, declared = HeldAction.declare(
        s, "alice", trigger_condition="when bob enters range",
        for_action="strike",
    )

    s, resolution = HeldAction.release_with_resolution(
        s, declared.id,
        trigger_observed="bob entered range",
        action_type="strike",
        targets=["bob"],
        parameters={"power_xmlid": "HKA"},
        result_payload={"hit": True, "stun_dealt": 12},
    )
    # Three new events: HeldActionReleased + ActionDeclared + ActionResolved
    assert resolution.released.held_event_id == declared.id
    assert resolution.new_declaration.combatant_id == "alice"
    assert resolution.new_declaration.action_type == "strike"
    assert resolution.new_resolution.declaration_event_id == resolution.new_declaration.id
    assert resolution.new_resolution.result_payload["hit"] is True
    # No more pending held actions
    assert HeldAction.get_pending(s, "alice") == []


def test_held_action_expires_when_combatant_next_phase_comes():
    """Per 6E2 p61, the held action is lost when the holder's next phase begins."""
    s = _session()
    s, declared = HeldAction.declare(
        s, "alice", trigger_condition="when bob attacks",
    )
    assert len(HeldAction.get_pending(s, "alice")) == 1

    s, expiries = HeldAction.expire_for_combatant_next_phase(s, "alice")
    assert len(expiries) == 1
    assert expiries[0].held_event_id == declared.id
    assert expiries[0].trigger_observed == "phase_expired"
    assert HeldAction.get_pending(s, "alice") == []


def test_release_on_event_does_not_release_non_matching_holds():
    """A held action whose match() returns False is unaffected."""
    s = _session()
    s, _ = HeldAction.declare(s, "alice", trigger_condition="when bob attacks")
    s, _ = HeldAction.declare(s, "bob", trigger_condition="when alice attacks")

    # Some unrelated event
    other = ActionDeclared(
        id=str(uuid.uuid4()), session_id="s1",
        sequence=len(s.event_log) + 1, timestamp=datetime.now(timezone.utc),
        author=make_author_combatant("alice"),
        combatant_id="alice", action_type="dodge", targets=[], parameters={},
    )
    from kirby_combat.session import apply_event
    s = apply_event(s, other)

    # Match: only release bob's hold (alice attacked, that's bob's trigger)
    def match(held, evt) -> bool:
        return (
            held.combatant_id == "bob"
            and evt.kind == "ActionDeclared"
            and getattr(evt, "combatant_id", "") == "alice"
            and getattr(evt, "action_type", "") == "dodge"
        )
    s, released = HeldAction.release_on_event(s, other, match=match)
    assert len(released) == 1
    # Alice's hold is still pending; bob's is released.
    assert len(HeldAction.get_pending(s, "alice")) == 1
    assert HeldAction.get_pending(s, "bob") == []
