"""Tests for resolve_mental_blast_in_session — the session-aware Mental
Blast wrapper.

Covers the gap this task closes: `mental_blast.py:45` computes
`target_stunned = stun_dealt > target.con` and discards it -- the same
defect `resolve_attack_in_session` fixed for physical attacks
(`kirby_combat/actions/recording.py`), in the one attack family that
wrapper doesn't cover. This wraps the pure `resolve_mental_blast`
(`kirby_combat/mental/mental_blast.py:26`) the same way
`resolve_attack_in_session` wraps `resolve_attack`: run the pure
calculation UNCHANGED, then emit an `ActionResolved` whose payload's
`status_changes` uses the SAME strings `resolution/status.py::
determine_status_changes` emits, so `statuses.py` folds a mental Stunned
with NO change to that module at all.
"""
from __future__ import annotations

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions.recording import (
    ACCEPTED_ACTION_KINDS, resolve_mental_blast_in_session,
)
from kirby_dice import FakeRoller
from kirby_combat.mental.mental_blast import resolve_mental_blast
from kirby_combat.session import CombatSession
from kirby_combat.statuses import statuses_for
from kirby_combat.template import CombatTemplate


def _mentalist(id_: str = "attacker", omcv: int = 8, dmcv: int = 3) -> "HeroCombatant":
    return synthetic_combatant(
        id=id_, name=id_, ocv=0, dcv=0, omcv=omcv, dmcv=dmcv,
        spd=4, dex=15, ego=18, str_=10, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=40,
        current_stun=30, current_body=15, current_end=40,
        is_mentalist=True,
    )


def _target(
    id_: str = "target", md: int = 0, con: int = 15,
    current_stun: int = 30, current_body: int = 15, max_body: int = 15,
) -> "HeroCombatant":
    return synthetic_combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=3, dmcv=5,
        spd=3, dex=12, ego=10, str_=15, con=con, pre=10, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=md, power_defense=0, flash_defense=0,
        max_stun=30, max_body=max_body, max_end=30,
        current_stun=current_stun, current_body=current_body, current_end=30,
    )


def _session(attacker, target) -> CombatSession:
    return CombatSession.create(
        id="s1", combatants=[attacker, target],
        scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


class TestEmitsExactlyOneActionResolved:
    def test_one_action_resolved_emitted(self):
        attacker, target = _mentalist(), _target(md=0)
        session = _session(attacker, target)

        new_session, _ = resolve_mental_blast_in_session(
            session, attacker, target, [4, 4, 4, 4],  # 16 STUN, CON 15
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"]
        assert len(resolved) == 1


class TestPayloadCarriesKindDiscriminator:
    def test_mental_blast_kind_is_not_one_of_the_attack_filter_values(self):
        # "mental_blast" is deliberately NOT in ACCEPTED_ACTION_KINDS -- a
        # Mental Blast is not an attack/strike/grab (see docstring).
        attacker, target = _mentalist(), _target(md=0)
        session = _session(attacker, target)

        new_session, _ = resolve_mental_blast_in_session(
            session, attacker, target, [4, 4, 4, 4],
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"][0]
        assert resolved.result_payload["kind"] == "mental_blast"
        assert "mental_blast" not in ACCEPTED_ACTION_KINDS


class TestStatusChangesStunnedThreshold:
    """6E2 p.106: Stunned when STUN dealt EXCEEDS CON -- '>', not '>='."""

    def test_stun_dealt_exceeds_con_sets_stunned(self):
        attacker = _mentalist()
        target = _target(md=0, con=15)
        session = _session(attacker, target)

        # 16 STUN vs CON 15: 16 > 15 -> Stunned
        new_session, result = resolve_mental_blast_in_session(
            session, attacker, target, [4, 4, 4, 4],
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"][0]
        assert result.stun_dealt == 16
        assert "Stunned" in resolved.result_payload["status_changes"]

    def test_stun_dealt_equal_to_con_is_not_stunned(self):
        attacker = _mentalist()
        target = _target(md=0, con=15)
        session = _session(attacker, target)

        # 15 STUN vs CON 15: 15 == 15 -> NOT Stunned (p.106 says "exceeds")
        new_session, result = resolve_mental_blast_in_session(
            session, attacker, target, [4, 4, 4, 3],
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"][0]
        assert result.stun_dealt == 15
        assert "Stunned" not in resolved.result_payload["status_changes"]


class TestStatusesForReportsStunnedWithoutTouchingStatusesPy:
    """The bar this task must clear: statuses_for reports 'stunned' after a
    mental attack, with kirby_combat/statuses.py completely unmodified --
    proving the payload strings, not the reader, carry the fix."""

    def test_statuses_for_reports_stunned_after_mental_attack(self):
        attacker = _mentalist()
        target = _target(md=0, con=15)
        session = _session(attacker, target)

        new_session, result = resolve_mental_blast_in_session(
            session, attacker, target, [4, 4, 4, 4],  # 16 > CON 15
        )

        assert result.target_stunned is True
        assert "stunned" in statuses_for(new_session, target.id)

    def test_statuses_for_does_not_report_stunned_at_the_boundary(self):
        attacker = _mentalist()
        target = _target(md=0, con=15)
        session = _session(attacker, target)

        new_session, result = resolve_mental_blast_in_session(
            session, attacker, target, [4, 4, 4, 3],  # 15 == CON 15
        )

        assert result.target_stunned is False
        assert "stunned" not in statuses_for(new_session, target.id)


class TestPureResolverUnaffected:
    """resolve_mental_blast (the pure resolver) must stay exactly as it was:
    identical result, no session, nothing emitted."""

    def test_pure_resolver_returns_identical_result_and_emits_nothing(self):
        attacker = _mentalist()
        target = _target(md=0, con=15)

        direct = resolve_mental_blast(attacker, target, [4, 4, 4, 4])

        session = _session(attacker, target)
        wrapped_session, wrapped_result = resolve_mental_blast_in_session(
            session, attacker, target, [4, 4, 4, 4],
        )

        assert wrapped_result == direct

        # Calling the pure resolver directly emits nothing at all.
        again = resolve_mental_blast(attacker, target, [4, 4, 4, 4])
        assert again == direct
