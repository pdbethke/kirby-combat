"""Tests for resolve_attack_in_session — the session-aware attack wrapper.

Covers the actual gap this task closes: `status_changes` (and damage
dealt) reaching the event log's ActionResolved.result_payload, where
today they die inside the pure AttackResult.
"""
from __future__ import annotations

import pytest

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions import resolve_attack
from kirby_combat.actions.recording import resolve_attack_in_session
from kirby_combat.dice import FakeRoller
from kirby_combat.models import AttackInput, AttackPower, DiceValues
from kirby_combat.session import CombatSession
from kirby_combat.template import CombatTemplate


def _attacker(con: int = 15) -> "HeroCombatant":
    return synthetic_combatant(
        id="attacker", name="Attacker",
        ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=con, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
        attacks=[
            AttackPower(
                xmlid="ENERGYBLAST", name="Energy Blast", damage_dice=10,
                half_die=False, plus_one=False,
                damage_type="normal", defense_type="ed", range_m=200,
                uses_str=False, str_min=0,
                armor_piercing=0, penetrating=0, increased_stun_mult=0,
            ),
        ],
    )


def _target(con: int = 15, current_stun: int = 30) -> "HeroCombatant":
    return synthetic_combatant(
        id="target", name="Target",
        ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=con, pre=15, rec=5,
        pd=0, ed=0, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=current_stun, current_body=15, current_end=30,
    )


def _session(attacker, target) -> CombatSession:
    return CombatSession.create(
        id="s1", combatants=[attacker, target],
        scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


def _hitting_attack(attacker, target) -> AttackInput:
    # Roll 9 to-hit (well within range); 10d6 normal EB, no defenses on
    # target so STUN dealt = 36, blowing through any reasonable CON.
    return AttackInput(
        attacker=attacker,
        target=target,
        power=attacker.attacks[0],
        distance_m=0,
        aim=None,
        dice=DiceValues(
            to_hit=[3, 3, 3],
            damage=[5, 4, 3, 6, 2, 4, 6, 3, 1, 2],
        ),
    )


class TestEmitsExactlyOneActionResolved:
    def test_one_action_resolved_emitted(self):
        attacker, target = _attacker(), _target()
        session = _session(attacker, target)
        attack = _hitting_attack(attacker, target)

        new_session, _ = resolve_attack_in_session(
            session, attack, session.template,
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"]
        assert len(resolved) == 1


class TestPayloadCarriesStatusChanges:
    def test_stunned_status_change_in_payload_when_stun_exceeds_con(self):
        # CON 15, 36 STUN rolled, no defenses -> stun_dealt 36 > CON 15 -> Stunned
        attacker, target = _attacker(), _target(con=15)
        session = _session(attacker, target)
        attack = _hitting_attack(attacker, target)

        new_session, result = resolve_attack_in_session(
            session, attack, session.template,
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"][0]
        assert "Stunned" in resolved.result_payload["status_changes"]
        # And it must actually match what the pure resolver computed —
        # not be independently re-derived.
        assert resolved.result_payload["status_changes"] == result.status_changes

    def test_payload_carries_hit_and_damage_dealt(self):
        attacker, target = _attacker(), _target()
        session = _session(attacker, target)
        attack = _hitting_attack(attacker, target)

        new_session, result = resolve_attack_in_session(
            session, attack, session.template,
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"][0]
        payload = resolved.result_payload
        assert payload["hit"] is True
        assert payload["stun_dealt"] == result.stun_dealt
        assert payload["body_dealt"] == result.body_dealt

    def test_knocked_out_derivable_from_payload_status_changes(self):
        # STUN starts at 5; 36 dealt drives stun_after deeply negative -> Knocked Out
        attacker, target = _attacker(con=15), _target(con=15, current_stun=5)
        session = _session(attacker, target)
        attack = _hitting_attack(attacker, target)

        new_session, result = resolve_attack_in_session(
            session, attack, session.template,
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"][0]
        assert "Knocked Out" in result.status_changes
        assert "Knocked Out" in resolved.result_payload["status_changes"]

    def test_no_status_changes_when_attack_misses(self):
        attacker, target = _attacker(), _target()
        session = _session(attacker, target)
        attack = AttackInput(
            attacker=attacker,
            target=target,
            power=attacker.attacks[0],
            distance_m=0,
            aim=None,
            dice=DiceValues(to_hit=[6, 6, 6]),  # guaranteed miss
        )

        new_session, result = resolve_attack_in_session(
            session, attack, session.template,
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"][0]
        assert resolved.result_payload["hit"] is False
        assert resolved.result_payload["status_changes"] == []


class TestPureResolverUntouched:
    def test_pure_resolve_attack_returns_identical_result_and_emits_nothing(self):
        attacker, target = _attacker(), _target()
        session = _session(attacker, target)
        attack = _hitting_attack(attacker, target)

        pure_result = resolve_attack(attack, session.template)

        # Fresh session/attack for the recording path so state isn't shared.
        attacker2, target2 = _attacker(), _target()
        session2 = _session(attacker2, target2)
        attack2 = _hitting_attack(attacker2, target2)
        _, recorded_result = resolve_attack_in_session(
            session2, attack2, session2.template,
        )

        assert pure_result == recorded_result

        # And the plain pure path never touches the session/event log at all.
        before = len(session.event_log)
        resolve_attack(attack, session.template)
        assert len(session.event_log) == before


class TestDeclarationEventIdWiring:
    def test_uses_provided_declaration_event_id_without_declaring_again(self):
        attacker, target = _attacker(), _target()
        session = _session(attacker, target)
        attack = _hitting_attack(attacker, target)

        new_session, _ = resolve_attack_in_session(
            session, attack, session.template,
            declaration_event_id="pre-existing-decl-id",
        )

        kinds = [e.kind for e in new_session.event_log]
        assert kinds.count("ActionDeclared") == 0
        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"][0]
        assert resolved.declaration_event_id == "pre-existing-decl-id"

    def test_declares_when_no_declaration_event_id_given(self):
        attacker, target = _attacker(), _target()
        session = _session(attacker, target)
        attack = _hitting_attack(attacker, target)

        new_session, _ = resolve_attack_in_session(
            session, attack, session.template,
        )

        kinds = [e.kind for e in new_session.event_log]
        assert kinds[-2:] == ["ActionDeclared", "ActionResolved"]
        declared, resolved = new_session.event_log[-2:]
        assert resolved.declaration_event_id == declared.id
