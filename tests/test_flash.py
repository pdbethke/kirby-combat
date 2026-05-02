"""Flash attack + per-phase recovery tests."""
import pytest

from fixtures.synthetic_hero import synthetic_combatant as Combatant
from kirby_combat.template import CombatTemplate
from kirby_combat.dice import FakeRoller
from kirby_combat.session import CombatSession
from kirby_combat.actions.flash import Flash, FlashResult


def _c(id_: str) -> Combatant:
    return Combatant(
        id=id_, name=id_, ocv=8, dcv=8, omcv=5, dmcv=5,
        spd=4, dex=20, ego=15, str_=15, con=15, pre=15, rec=5,
        pd=5, ed=5, rpd=0, red=0, md=5, power_defense=0, flash_defense=3,
        max_stun=30, max_body=15, max_end=30,
        current_stun=30, current_body=15, current_end=30,
    )


def _session() -> CombatSession:
    return CombatSession.create(
        id="s1", combatants=[_c("alice"), _c("bob")],
        scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=FakeRoller([]),
    ).start()


# ---- apply ----

def test_flash_segments_equal_body_dealt_minus_flash_defense():
    s = _session()
    s2, result = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=8, flash_defense=3,
    )
    assert isinstance(result, FlashResult)
    assert result.segments_remaining == 5     # 8 - 3
    assert result.method == "applied"
    assert result.cleared is False
    assert result.sense_group == "sight"


def test_flash_zero_segments_when_defense_blocks_all():
    s = _session()
    s2, result = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=2, flash_defense=5,
    )
    assert result.segments_remaining == 0
    assert result.cleared is True            # nothing landed


def test_flash_emits_action_declared_resolved_and_flash_applied():
    s = _session()
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=8, flash_defense=3,
    )
    kinds = [e.kind for e in s2.event_log]
    assert "ActionDeclared" in kinds
    assert "ActionResolved" in kinds
    assert "FlashApplied" in kinds


# ---- is_flashed ----

def test_is_flashed_false_initially():
    s = _session()
    flashed, groups = Flash.is_flashed(s, "bob")
    assert flashed is False
    assert groups == {}


def test_is_flashed_returns_remaining_segments():
    s = _session()
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=8, flash_defense=3,
    )
    flashed, groups = Flash.is_flashed(s2, "bob")
    assert flashed is True
    assert groups == {"sight": 5}


def test_is_flashed_specific_sense_group():
    s = _session()
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=8, flash_defense=3,
    )
    flashed, groups = Flash.is_flashed(s2, "bob", sense_group="hearing")
    assert flashed is False
    assert groups == {}


# ---- multiple sense groups ----

def test_multiple_sense_groups_tracked_independently():
    s = _session()
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=8, flash_defense=3,
    )
    s3, _ = Flash.apply(
        s2, attacker_id="alice", target_id="bob",
        sense_group="hearing", body_dealt=6, flash_defense=3,
    )
    flashed, groups = Flash.is_flashed(s3, "bob")
    assert flashed is True
    assert groups == {"sight": 5, "hearing": 3}


# ---- recovery ----

def test_recover_one_segment_per_phase():
    s = _session()
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=8, flash_defense=3,
    )
    s3, result = Flash.recover(s2, target_id="bob", sense_group="sight")
    assert result.method == "recovered"
    assert result.segments_remaining == 4    # 5 - 1
    assert result.cleared is False
    flashed, groups = Flash.is_flashed(s3, "bob")
    assert groups == {"sight": 4}


def test_recover_clears_when_reaches_zero():
    s = _session()
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=4, flash_defense=3,    # 1 segment
    )
    s3, result = Flash.recover(s2, target_id="bob", sense_group="sight")
    assert result.cleared is True
    assert result.segments_remaining == 0
    assert result.method == "fully_recovered"
    flashed, groups = Flash.is_flashed(s3, "bob")
    assert flashed is False
    assert groups == {}


def test_recover_multiple_segments_at_once():
    s = _session()
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=8, flash_defense=3,
    )
    s3, result = Flash.recover(
        s2, target_id="bob", sense_group="sight", segments_to_recover=3,
    )
    assert result.segments_remaining == 2     # 5 - 3
    assert result.cleared is False


def test_recover_when_not_flashed_raises():
    s = _session()
    with pytest.raises(ValueError, match="not flashed"):
        Flash.recover(s, target_id="bob", sense_group="sight")


def test_recover_specific_sense_does_not_clear_others():
    s = _session()
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=8, flash_defense=3,
    )
    s3, _ = Flash.apply(
        s2, attacker_id="alice", target_id="bob",
        sense_group="hearing", body_dealt=6, flash_defense=3,
    )
    s4, _ = Flash.recover(s3, target_id="bob", sense_group="sight", segments_to_recover=5)
    flashed, groups = Flash.is_flashed(s4, "bob")
    assert flashed is True
    assert groups == {"hearing": 3}    # sight cleared, hearing unaffected


# ---- modifiers ----

def test_flash_hth_modifiers_half_ocv_half_dcv():
    """Per 6E2 p127: HTH attacks vs flashed target → ½ OCV / ½ DCV."""
    s = _session()
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=8, flash_defense=3,
    )
    # Default attack_type is "hth"
    mods = Flash.modifiers(s2, "bob")
    assert mods == {"ocv_factor": 0.5, "dcv_factor": 0.5}
    # Explicit "hth" matches default
    mods_hth = Flash.modifiers(s2, "bob", attack_type="hth")
    assert mods_hth == {"ocv_factor": 0.5, "dcv_factor": 0.5}


def test_flash_ranged_modifiers_zero_ocv_half_dcv_per_6e2_p127():
    """Per 6E2 p127 §Inability To Sense An Opponent:
    Ranged attacks vs flashed target → 0 OCV / ½ DCV (cannot meaningfully aim).
    """
    s = _session()
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=8, flash_defense=3,
    )
    mods = Flash.modifiers(s2, "bob", attack_type="ranged")
    assert mods == {"ocv_factor": 0.0, "dcv_factor": 0.5}


def test_modifiers_empty_when_not_flashed():
    s = _session()
    assert Flash.modifiers(s, "bob") == {}


def test_modifiers_clear_after_full_recovery():
    s = _session()
    s2, _ = Flash.apply(
        s, attacker_id="alice", target_id="bob",
        sense_group="sight", body_dealt=4, flash_defense=3,
    )
    s3, _ = Flash.recover(s2, target_id="bob", sense_group="sight")
    assert Flash.modifiers(s3, "bob") == {}
