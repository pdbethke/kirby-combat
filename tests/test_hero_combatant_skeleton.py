"""Skeleton tests for HeroCombatant — confirms the bridge LOADS real
HDC characters cleanly, even before combat_stats() / attack_view() /
defense_view() are filled in.

The spec calls for a richer test suite once view-builders land
(asserting derived stats match the source HDC). This file is the
landing-strip — it proves we can `from_hdc(...)` an actual character
without exploding.

Test fixtures point at HDC files in the user's local workspace. If
those paths don't exist (CI without the workspace), the tests are
skipped rather than failed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kirby_combat.hero_view import HeroCombatant, HeroCombatState, HeroCombatStats


# Fixtures — the four characters we just imported into character-json/.
# These are real HDC files outside the kirby-combat repo; CI may not
# have them, so each test that uses them is skipif-guarded.
PC_DIR = Path(
    "/home/pdbethke/Documents/Champions/Pcs"
)
CV1_DIR = Path(
    "/home/pdbethke/Documents/Champions/Docs/CV1HDFiles"
)


def _need(path: Path) -> Path:
    """Skip the calling test if the HDC fixture isn't available."""
    if not path.exists():
        pytest.skip(f"HDC fixture not present: {path}")
    return path


def test_loads_stone_cold():
    """from_hdc() builds a HeroCombatant from Stone_Cold.hdc."""
    hdc = _need(PC_DIR / "Stone_Cold.hdc")

    combatant = HeroCombatant.from_hdc(hdc)

    assert combatant.hero is not None
    assert combatant.hero.name == "Stone Cold"
    assert combatant.id == "stone_cold"
    # Power list is loaded from HD's framework-aware loader.
    # Stone Cold has 16 powers including the Elemental Control: Ice
    # multipower.
    assert len(combatant.hero.powers) >= 10, (
        f"expected ~16 powers on Stone Cold, got {len(combatant.hero.powers)}"
    )


def test_loads_gyre():
    hdc = _need(PC_DIR / "Gyre.hdc")
    c = HeroCombatant.from_hdc(hdc)
    assert c.hero.name == "Gyre"
    assert c.id == "gyre"


def test_state_is_isolated_per_combatant():
    """Two HeroCombatants from the same HDC have independent state.

    Locked decision §7 #1 — hero is owned, not shared. (LoadedHero is
    shared from disk, but each combatant has its own state.)
    """
    hdc = _need(PC_DIR / "Stone_Cold.hdc")
    a = HeroCombatant.from_hdc(hdc, id="stone_cold_alpha")
    b = HeroCombatant.from_hdc(hdc, id="stone_cold_beta")

    assert a is not b
    assert a.state is not b.state
    assert a.id != b.id


def test_combat_state_is_blank_at_load():
    hdc = _need(PC_DIR / "Stone_Cold.hdc")
    c = HeroCombatant.from_hdc(hdc)

    assert c.state.statuses == set()
    assert c.state.drains == {}
    assert c.state.aids == {}
    assert c.state.used_charges == {}
    assert c.state.aborted is False
    assert c.state.last_acted_segment is None
    assert c.state.active_slot_per_framework == {}


def test_combat_stats_raises_until_implemented():
    """combat_stats() is the next commit. For now it raises so callers
    don't silently get garbage."""
    hdc = _need(PC_DIR / "Stone_Cold.hdc")
    c = HeroCombatant.from_hdc(hdc)

    with pytest.raises(NotImplementedError):
        c.combat_stats()


def test_attack_view_raises_until_implemented():
    hdc = _need(PC_DIR / "Stone_Cold.hdc")
    c = HeroCombatant.from_hdc(hdc)

    with pytest.raises(NotImplementedError):
        c.attack_view("CONEOFCOLD")


def test_defense_view_raises_until_implemented():
    hdc = _need(PC_DIR / "Stone_Cold.hdc")
    c = HeroCombatant.from_hdc(hdc)

    with pytest.raises(NotImplementedError):
        c.defense_view()


def test_dataclasses_are_constructible():
    """Sanity: the new dataclasses are constructible without HDC at all.
    Useful for unit tests that synthesize state directly."""
    state = HeroCombatState(current_stun=40, current_body=14, current_end=40)
    assert state.current_stun == 40
    assert state.statuses == set()

    stats = HeroCombatStats(
        ocv=9, dcv=8, omcv=4, dmcv=4,
        spd=5, dex=23, ego=15, str_=20, con=20, pre=20, rec=8,
        pd=10, ed=10, rpd=4, red=4, md=5,
        power_defense=0, flash_defense=0,
        max_stun=40, max_body=14, max_end=40,
    )
    assert stats.ocv == 9
