"""TDD tests for AVAD / NND all-or-nothing defense resolution (6E1 p328)."""
from __future__ import annotations

import pytest

from kirby_combat.models import AttackPower, DefenseItem
from kirby_combat.resolution.defense import compute_defense, _target_has_named_defense
from fixtures.synthetic_hero import synthetic_combatant


# ---------------------------------------------------------------------------
# Helper: build an NND/AVAD attack power
# ---------------------------------------------------------------------------

def _nnd(defense: str) -> AttackPower:
    return AttackPower(
        xmlid="ENERGYBLAST",
        name="NND Blast",
        damage_dice=12,
        half_die=False,
        plus_one=False,
        damage_type="normal",
        defense_type="ed",
        range_m=75,
        uses_str=False,
        str_min=0,
        armor_piercing=0,
        penetrating=0,
        increased_stun_mult=0,
        avad=True,
        avad_defense=defense,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_avad_full_damage_when_target_lacks_named_defense():
    """AVAD vs target without Power Defense → total_defense=0 (full damage gets through)."""
    target = synthetic_combatant(
        id="target1",
        name="Armored Goon",
        ed=20,
        red=15,
        power_defense=0,  # explicitly no power defense
    )
    prof = compute_defense(target, _nnd("Power Defense"))
    assert prof.total_defense == 0, (
        f"Expected 0 (AVAD, target lacks named defense), got {prof.total_defense}; "
        f"audit={prof.audit}"
    )


def test_avad_blocks_entirely_when_target_has_named_defense():
    """AVAD vs target WITH Power Defense → total_defense >= 10_000 (all-or-nothing block)."""
    target = synthetic_combatant(
        id="target2",
        name="Brick With Power Defense",
        ed=20,
        red=15,
        power_defense=10,
    )
    prof = compute_defense(target, _nnd("Power Defense"))
    assert prof.total_defense >= 10_000, (
        f"Expected ≥10000 (AVAD, target has named defense), got {prof.total_defense}; "
        f"audit={prof.audit}"
    )


def test_matcher_defaults_to_lacks_for_unmappable_freetext():
    """Exotic free-text defense the engine can't map → defaults to False (target lacks it)."""
    target = synthetic_combatant(
        id="target3",
        name="Normal Joe",
        ed=10,
    )
    result = _target_has_named_defense(
        target,
        "Life Support (Safe Environment: Intense Heat) Or Fire/Heat Powers",
    )
    assert result is False, f"Expected False for unmappable free-text, got {result}"


def test_non_avad_attack_unchanged():
    """Non-AVAD attacks still use normal PD/ED defense — AVAD path must not fire."""
    plain = AttackPower(
        xmlid="ENERGYBLAST",
        name="Blast",
        damage_dice=12,
        half_die=False,
        plus_one=False,
        damage_type="normal",
        defense_type="ed",
        range_m=75,
        uses_str=False,
        str_min=0,
        armor_piercing=0,
        penetrating=0,
        increased_stun_mult=0,
        # avad defaults to False
    )
    target = synthetic_combatant(
        id="target4",
        name="Normal Target",
        ed=25,
    )
    prof = compute_defense(target, plain)
    assert prof.total_defense > 0, (
        f"Expected ED to apply for non-AVAD attack, got total_defense={prof.total_defense}; "
        f"audit={prof.audit}"
    )


def test_avad_audit_mentions_named_defense():
    """AVAD resolution must include an audit entry naming the defense tested."""
    target = synthetic_combatant(id="t5", name="Foo", power_defense=5)
    prof = compute_defense(target, _nnd("Power Defense"))
    combined = " ".join(prof.audit).lower()
    assert "power defense" in combined, (
        f"Expected 'power defense' in audit; got: {prof.audit}"
    )


def test_avad_tag_has_in_defense_tags():
    """When target has the named defense, defense_tags must contain 'avad:has'."""
    target = synthetic_combatant(id="t6", name="Protected", power_defense=5)
    prof = compute_defense(target, _nnd("Power Defense"))
    assert "avad:has" in prof.defense_tags, (
        f"Expected 'avad:has' in defense_tags; got {prof.defense_tags}"
    )


def test_avad_tag_lacks_in_defense_tags():
    """When target lacks the named defense, defense_tags must contain 'avad:lacks'."""
    target = synthetic_combatant(id="t7", name="Unprotected", power_defense=0)
    prof = compute_defense(target, _nnd("Power Defense"))
    assert "avad:lacks" in prof.defense_tags, (
        f"Expected 'avad:lacks' in defense_tags; got {prof.defense_tags}"
    )
