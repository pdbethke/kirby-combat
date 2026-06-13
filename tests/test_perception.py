"""Combat perception tests (spec 2026-06-13-combat-perception-design §1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from kirby_combat.hero_view import HeroCombatant

# Committed in-repo fixture (same one test_hero_combatant_skeleton uses).
INFERNA_HDC = Path(__file__).parent / "fixtures" / "Inferna.hdc"


def _inferna() -> HeroCombatant:
    if not INFERNA_HDC.exists():
        pytest.skip(f"HDC fixture not present: {INFERNA_HDC}")
    return HeroCombatant.from_hdc(str(INFERNA_HDC))


def test_every_character_has_normal_sight():
    senses = _inferna().senses()
    sight = [s for s in senses if s.xmlid == "NORMALSIGHT"]
    assert len(sight) == 1
    assert sight[0].group == "sight"
    assert sight[0].is_targeting is True


def test_inferna_has_infrared_in_the_sight_group():
    # Inferna.hdc carries INFRAREDPERCEPTION (a Sight-Group targeting sense).
    senses = _inferna().senses()
    ir = [s for s in senses if s.xmlid == "INFRAREDPERCEPTION"]
    assert len(ir) == 1
    assert ir[0].group == "sight"          # IR is bought into the Sight Group
    assert ir[0].is_targeting is True


def test_senses_are_targeting_only_set():
    # senses() returns only Targeting senses (the combat-relevant ones).
    for s in _inferna().senses():
        assert s.is_targeting is True


# --- Task 2: PER + Stealth roll helpers ---------------------------------------

from kirby_combat.perception import per_roll_target, _roll_3d6_succeeds
from kirby_combat.dice import RandomRoller


def test_per_target_is_9_plus_int_over_5():
    hc = _inferna()
    int_val = int(hc.hero.characteristic_value("INT"))
    assert per_roll_target(hc) == 9 + int_val // 5


def test_skill_roll_value_returns_none_when_absent():
    # A character without STEALTH returns None (caller treats as auto-perceived).
    hc = _inferna()
    val = hc.skill_roll_value("DEFINITELY_NOT_A_SKILL")
    assert val is None


def test_3d6_succeeds_is_roll_le_target():
    # roller seeded so the 3d6 is deterministic; success iff sum <= target.
    r = RandomRoller(seed=1)
    rolled = sum(RandomRoller(seed=1).roll_dice(3))   # same seed → same roll
    assert _roll_3d6_succeeds(target=rolled, roller=r) is True
    r2 = RandomRoller(seed=1)
    assert _roll_3d6_succeeds(target=rolled - 1, roller=r2) is False
