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


def test_combat_stats_returns_sane_values():
    """combat_stats() reads cost-engine characteristic values from the
    LoadedHero. Stone Cold is a built superhero — assert sane
    integers, not specific pinned numbers."""
    hdc = _need(PC_DIR / "Stone_Cold.hdc")
    c = HeroCombatant.from_hdc(hdc)

    s = c.combat_stats()
    assert s.str_ >= 10
    assert s.dex >= 10
    assert s.ocv >= 3
    assert s.dcv >= 3
    assert s.spd >= 2
    assert s.max_stun >= 10
    assert s.max_body >= 5
    assert s.max_end >= 10


def test_attack_view_returns_attack_power():
    """attack_view() builds an AttackPower record from a hero power."""
    hdc = _need(PC_DIR / "Stone_Cold.hdc")
    c = HeroCombatant.from_hdc(hdc)

    atk = c.attack_view("ENERGYBLAST")
    assert atk.xmlid == "ENERGYBLAST"
    assert atk.damage_dice >= 1
    assert atk.damage_type == "normal"
    assert atk.defense_type == "ed"
    assert atk.range_m > 0


def test_defense_view_returns_list():
    """defense_view() returns a list of DefenseItem (possibly empty)."""
    hdc = _need(PC_DIR / "Stone_Cold.hdc")
    c = HeroCombatant.from_hdc(hdc)

    items = c.defense_view()
    assert isinstance(items, list)


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


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — engine accepts HeroCombatant directly via uniform combat_stats()
# interface (no to_legacy bridge needed)
# ─────────────────────────────────────────────────────────────────────────────


def test_legacy_combatant_has_combat_stats_shim():
    """Legacy Combatant.combat_stats() returns self — uniform read path."""
    from kirby_combat.models import Combatant

    c = Combatant(
        id="t", name="Test", ocv=8, dcv=8, omcv=3, dmcv=3, spd=4,
        dex=20, ego=10, str_=20, con=20, pre=15, rec=8,
        pd=10, ed=10, rpd=0, red=0, md=0,
        power_defense=0, flash_defense=0,
        max_stun=40, max_body=12, max_end=40,
        current_stun=40, current_body=12, current_end=40,
    )
    assert c.combat_stats() is c
    assert c.state is c
    # Both read paths return same values
    assert c.combat_stats().ocv == c.ocv == 8
    assert c.state.current_stun == c.current_stun == 40


def test_attack_input_accepts_hero_combatant():
    """AttackInput type-widening: attacker/target may be either shape."""
    from kirby_combat.actions import AttackInput
    from kirby_combat.hero_view import HeroCombatant, HeroCombatState
    from kirby_combat.models import AttackPower, DiceValues

    class _StubHero:
        name = "test"
        powers: list = []  # noqa: RUF012

        def characteristic_value(self, xmlid: str) -> int:
            return {"OCV": 5, "DCV": 5, "STUN": 30, "BODY": 10, "END": 30}.get(
                xmlid.upper(), 0,
            )

    hc = HeroCombatant(
        id="hero", hero=_StubHero(),  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=30, current_body=10, current_end=30),
    )
    # Just confirm we can construct AttackInput with a HeroCombatant
    # and that it exposes combat_stats() via the new uniform interface.
    power = AttackPower(
        xmlid="ENERGYBLAST", name="Test Blast", damage_dice=4,
        half_die=False, plus_one=False, damage_type="normal",
        defense_type="ed", range_m=20.0, uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
    )
    ai = AttackInput(
        attacker=hc, target=hc, power=power,
        distance_m=10.0, aim=None,
        dice=DiceValues(to_hit=[3, 3, 3], damage=[3, 3, 3, 3]),
    )
    # Uniform read regardless of attacker shape
    assert ai.attacker.combat_stats().ocv == 5
    assert ai.attacker.state.current_stun == 30
