"""Entangle action tests."""
import pytest

from fixtures.synthetic_hero import synthetic_combatant as Combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller
from kirby_combat.session import CombatSession
from kirby_combat.actions.entangle import Entangle, EntangleResult


def _c(id_: str, str_: int = 20) -> Combatant:
    return Combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=str_, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=0,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _session() -> CombatSession:
    return CombatSession.create(
        id="s1",
        combatants=[_c("alice", str_=30), _c("bob", str_=20)],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


# ---- apply ----

def test_apply_creates_entangle_state_on_target():
    s = _session()
    s2, result = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    assert isinstance(result, EntangleResult)
    assert result.target_id == "bob"
    assert result.method == "applied"
    assert result.body_remaining == 8
    assert result.escaped is False


def test_apply_emits_entangleapplied_event():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    kinds = [e.kind for e in s2.event_log]
    assert "EntangleApplied" in kinds
    # Most recent EntangleApplied should reference bob
    last_ea = next(e for e in reversed(s2.event_log) if e.kind == "EntangleApplied")
    assert last_ea.target_id == "bob"
    assert last_ea.entangle_body == 8


def test_apply_emits_action_declared_and_resolved_too():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    kinds = [e.kind for e in s2.event_log]
    assert "ActionDeclared" in kinds
    assert "ActionResolved" in kinds


# ---- is_entangled ----

def test_is_entangled_false_when_no_entangle():
    s = _session()
    assert Entangle.is_entangled(s, "bob") == (False, None)


def test_is_entangled_returns_remaining_body():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    is_e, body = Entangle.is_entangled(s2, "bob")
    assert is_e is True
    assert body == 8


# ---- modifiers ----

def test_modifiers_zero_dcv_half_ocv_when_entangled():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    mods = Entangle.modifiers(s2, "bob")
    assert mods == {"ocv_factor": 0.5, "dcv_factor": 0.0}


def test_modifiers_empty_when_not_entangled():
    s = _session()
    assert Entangle.modifiers(s, "bob") == {}


# ---- escape: casual STR ----

def test_casual_str_escape_reduces_body_by_str_over_10_minus_pd():
    # str_used=30 → 30/10 = 3 raw → minus PD 4 → 0 damage
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, esc = Entangle.escape_attempt(
        s2, target_id="bob", str_used=30, escape_type="casual",
    )
    assert esc.method == "casual_str"
    assert esc.damage_to_entangle_body == 0      # 30//10 = 3, minus pd 4 → 0
    assert esc.body_remaining == 8
    assert esc.escaped is False


def test_casual_str_escape_with_high_str_chips_away():
    # str_used=80 → 80/10 = 8 raw → minus PD 4 → 4 damage
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, esc = Entangle.escape_attempt(
        s2, target_id="bob", str_used=80, escape_type="casual",
    )
    assert esc.damage_to_entangle_body == 4
    assert esc.body_remaining == 4
    assert esc.escaped is False


# ---- escape: full STR ----

def test_full_str_escape_uses_str_over_5_minus_pd():
    # str_used=30 → 30/5 = 6 raw → minus pd 4 → 2 damage
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, esc = Entangle.escape_attempt(
        s2, target_id="bob", str_used=30, escape_type="full",
    )
    assert esc.method == "full_str"
    assert esc.damage_to_entangle_body == 2
    assert esc.body_remaining == 6


def test_full_str_escape_can_break_free_in_one_attempt():
    # str_used=80 → 80/5 = 16 raw → minus pd 4 → 12 damage. Body 8 → escapes.
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, esc = Entangle.escape_attempt(
        s2, target_id="bob", str_used=80, escape_type="full",
    )
    assert esc.escaped is True
    assert esc.body_remaining == 0


def test_escape_emits_entangleescape_event():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, _ = Entangle.escape_attempt(
        s2, target_id="bob", str_used=80, escape_type="full",
    )
    kinds = [e.kind for e in s3.event_log]
    assert "EntangleEscape" in kinds


def test_escape_when_not_entangled_raises():
    s = _session()
    with pytest.raises(ValueError, match="not entangled"):
        Entangle.escape_attempt(
            s, target_id="bob", str_used=30, escape_type="full",
        )


def test_unknown_escape_type_raises():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    with pytest.raises(ValueError, match="escape_type"):
        Entangle.escape_attempt(
            s2, target_id="bob", str_used=30, escape_type="bogus",
        )


# ---- multi-attempt scenario ----

def test_multiple_casual_attempts_eventually_break_through():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=2, entangle_ed=4,    # weak entangle
    )
    # str_used=80 casual → 80/10 = 8 raw - pd 2 = 6 damage. After 1 attempt: body=2.
    s3, esc1 = Entangle.escape_attempt(s2, target_id="bob", str_used=80, escape_type="casual")
    assert esc1.body_remaining == 2
    assert esc1.escaped is False

    # Another 6 damage attempt → body 2 - 6 → escaped, body_remaining=0
    s4, esc2 = Entangle.escape_attempt(s3, target_id="bob", str_used=80, escape_type="casual")
    assert esc2.escaped is True
    assert esc2.body_remaining == 0

    # No longer entangled
    assert Entangle.is_entangled(s4, "bob") == (False, None)


def test_modifiers_clear_after_escape():
    s = _session()
    s2, _ = Entangle.apply(
        s, attacker_id="alice", target_id="bob",
        entangle_body=8, entangle_pd=4, entangle_ed=4,
    )
    s3, _ = Entangle.escape_attempt(s2, target_id="bob", str_used=80, escape_type="full")
    assert Entangle.modifiers(s3, "bob") == {}
