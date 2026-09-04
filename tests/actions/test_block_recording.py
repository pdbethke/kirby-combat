"""Tests for resolve_block_in_session — the session-aware Block wrapper.

Covers the gap this task closes: `Block.resolve` (`actions/reactive/block.py`)
is a pure calculator with no session, so a Block's outcome never reaches the
event log, and `Block.acts_first_priority` (6E2 p.60, "ACTING FIRST") has no
live caller anywhere. This wraps the pure resolver the same way
`resolve_attack_in_session` wraps `resolve_attack` (see
`kirby_combat/actions/recording.py`): run the pure calculation unchanged,
then emit an `ActionResolved` describing it.
"""
from __future__ import annotations

from fixtures.synthetic_hero import synthetic_combatant
from kirby_combat.actions.reactive.block import Block, BlockResult
from kirby_combat.actions.recording import resolve_block_in_session
from kirby_dice import FakeRoller
from kirby_combat.session import CombatSession
from kirby_combat.template import CombatTemplate


def _c(id_: str, ocv: int = 8, dcv: int = 8, dex: int = 20) -> "HeroCombatant":
    return synthetic_combatant(
        id=id_, name=id_, ocv=ocv, dcv=dcv, omcv=5, dmcv=5,
        spd=4, dex=dex, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _session() -> CombatSession:
    return CombatSession.create(
        id="s1",
        combatants=[_c("alice"), _c("bob")],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


class TestEmitsExactlyOneActionResolved:
    def test_one_action_resolved_emitted(self):
        session = _session()

        new_session, _, _ = resolve_block_in_session(
            session,
            blocker_id="alice", attacker_id="bob",
            blocker_ocv=10, blocker_dice=[3, 3, 3], attacker_ocv=8,
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"]
        assert len(resolved) == 1


class TestPayloadCarriesOutcome:
    def test_successful_block_payload(self):
        session = _session()

        new_session, result, _ = resolve_block_in_session(
            session,
            blocker_id="alice", attacker_id="bob",
            blocker_ocv=10, blocker_dice=[3, 3, 3], attacker_ocv=8,
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"][0]
        payload = resolved.result_payload
        assert payload["success"] is True
        assert payload["blocker_id"] == "alice"
        assert payload["attacker_id"] == "bob"
        assert payload["blocker_roll"] == result.blocker_roll
        assert payload["blocker_margin"] == result.blocker_margin
        assert payload["attacker_ocv"] == result.attacker_ocv
        assert payload["blocker_ocv"] == result.blocker_ocv

    def test_failed_block_payload(self):
        session = _session()

        new_session, result, priority = resolve_block_in_session(
            session,
            blocker_id="alice", attacker_id="bob",
            blocker_ocv=8, blocker_dice=[4, 4, 4], attacker_ocv=10,
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"][0]
        assert resolved.result_payload["success"] is False
        assert result.success is False
        assert priority == {}


class TestPayloadCarriesKindDiscriminator:
    """A Block is not an attack, strike, or grab; it does not belong in
    kirby-api's attack filter (`situation_builder.py:687-688`:
    `kind not in ("attack", "strike", "grab")` -> skipped). Rather than
    picking one of those three values to slip past that filter — which
    would mislabel a Block as something it isn't — this payload carries
    the honest, distinct value "block". That means kirby-api's current
    filter does not consume it yet; extending that filter is kirby-api's
    call and out of scope here. This test pins the honest value, not
    membership in the accepted-by-kirby-api set.
    """
    def test_kind_is_block(self):
        session = _session()

        new_session, _, _ = resolve_block_in_session(
            session,
            blocker_id="alice", attacker_id="bob",
            blocker_ocv=10, blocker_dice=[3, 3, 3], attacker_ocv=8,
        )

        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"][0]
        assert resolved.result_payload["kind"] == "block"


class TestActsFirstPriorityHasLiveCaller:
    """`Block.acts_first_priority` (6E2 p.60) previously had no live caller
    anywhere in kirby_combat. `resolve_block_in_session` is that caller: it
    computes the priority mapping from the just-resolved `BlockResult` and
    hands it back to its caller as the third return value, so a driver that
    owns an `Encounter` can merge it into `Encounter.acts_first` itself.
    """
    def test_successful_block_returns_acts_first_priority(self):
        session = _session()

        _, result, priority = resolve_block_in_session(
            session,
            blocker_id="alice", attacker_id="bob",
            blocker_ocv=10, blocker_dice=[3, 3, 3], attacker_ocv=8,
        )

        assert result.success is True
        assert priority == {"alice": "bob"}

    def test_failed_block_returns_empty_priority(self):
        session = _session()

        _, result, priority = resolve_block_in_session(
            session,
            blocker_id="alice", attacker_id="bob",
            blocker_ocv=8, blocker_dice=[4, 4, 4], attacker_ocv=10,
        )

        assert result.success is False
        assert priority == {}


class TestPureResolverUntouched:
    def test_pure_resolve_returns_identical_result_and_emits_nothing(self):
        pure_result = Block.resolve(
            blocker_ocv=10, blocker_dice=[3, 3, 3], attacker_ocv=8,
        )

        session = _session()
        _, recorded_result, _ = resolve_block_in_session(
            session,
            blocker_id="alice", attacker_id="bob",
            blocker_ocv=10, blocker_dice=[3, 3, 3], attacker_ocv=8,
        )

        assert pure_result == recorded_result

        before = len(session.event_log)
        Block.resolve(blocker_ocv=10, blocker_dice=[3, 3, 3], attacker_ocv=8)
        assert len(session.event_log) == before


class TestDeclarationEventIdWiring:
    def test_uses_provided_declaration_event_id_without_declaring_again(self):
        session = _session()

        new_session, _, _ = resolve_block_in_session(
            session,
            blocker_id="alice", attacker_id="bob",
            blocker_ocv=10, blocker_dice=[3, 3, 3], attacker_ocv=8,
            declaration_event_id="pre-existing-decl-id",
        )

        kinds = [e.kind for e in new_session.event_log]
        assert kinds.count("AbortDeclared") == 0
        resolved = [e for e in new_session.event_log if e.kind == "ActionResolved"][0]
        assert resolved.declaration_event_id == "pre-existing-decl-id"

    def test_declares_abort_when_no_declaration_event_id_given(self):
        session = _session()

        new_session, _, _ = resolve_block_in_session(
            session,
            blocker_id="alice", attacker_id="bob",
            blocker_ocv=10, blocker_dice=[3, 3, 3], attacker_ocv=8,
        )

        kinds = [e.kind for e in new_session.event_log]
        assert kinds[-2:] == ["AbortDeclared", "ActionResolved"]
        declared, resolved = new_session.event_log[-2:]
        assert resolved.declaration_event_id == declared.id
