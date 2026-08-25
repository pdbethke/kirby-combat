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

from tests.corpus import require_authored


# Real HD character files come from the authored corpus, never from the
# repository and never from a path into a maintainer's home. See
# tests/corpus.py for why, and what to set to run these.


def test_loads_a_character_from_hdc():
    """from_hdc() builds a HeroCombatant from a real HD file."""
    hdc = require_authored("Ravel")

    combatant = HeroCombatant.from_hdc(hdc)

    assert combatant.hero is not None
    assert combatant.hero.name.startswith("Ravel")
    assert combatant.id.startswith("ravel")
    # Power list is loaded from HD's framework-aware loader, so framework
    # slots arrive as powers too.
    assert len(combatant.hero.powers) >= 10, (
        f"expected a framework-bearing build, got {len(combatant.hero.powers)} powers"
    )


def test_loads_a_second_distinct_character():
    hdc = require_authored("Bokor")
    c = HeroCombatant.from_hdc(hdc)
    assert c.hero.name == "Bokor"
    assert c.id == "bokor"


def test_state_is_isolated_per_combatant():
    """Two HeroCombatants from the same HDC have independent state.

    Locked decision §7 #1 — hero is owned, not shared. (LoadedHero is
    shared from disk, but each combatant has its own state.)
    """
    hdc = require_authored("Ravel")
    a = HeroCombatant.from_hdc(hdc, id="character_alpha")
    b = HeroCombatant.from_hdc(hdc, id="character_beta")

    assert a is not b
    assert a.state is not b.state
    assert a.id != b.id


def test_combat_state_is_blank_at_load():
    hdc = require_authored("Ravel")
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
    LoadedHero. The character is a built superhero — assert sane
    integers, not specific pinned numbers."""
    hdc = require_authored("Ravel")
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
    hdc = require_authored("Ravel")
    c = HeroCombatant.from_hdc(hdc)

    atk = c.attack_view("ENERGYBLAST")
    assert atk.xmlid == "ENERGYBLAST"
    assert atk.damage_dice >= 1
    assert atk.damage_type == "normal"
    assert atk.defense_type == "ed"
    assert atk.range_m > 0


def test_defense_view_returns_list():
    """defense_view() returns a list of DefenseItem (possibly empty)."""
    hdc = require_authored("Ravel")
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
    # NOT synthetic: this test asserts the flat StatBlockCombatant's own
    # combat_stats()/state shim (identity: `c.combat_stats() is c`), which
    # is specific to the flat shape.
    from kirby_combat.models import StatBlockCombatant

    c = StatBlockCombatant(
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


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — committed-fixture integration tests
# Use ``require_authored("Bokor")`` (in-repo) so these run in CI without host-path
# dependencies. Exercises the full HD-shaped path: from_hdc → views →
# AttackInput → engine.resolve_attack → AttackResult.
# ─────────────────────────────────────────────────────────────────────────────


def test_loads_from_the_authored_corpus():
    """Sanity: committed HDC fixture loads cleanly."""
    c = HeroCombatant.from_hdc(require_authored("Bokor"))
    assert c.hero is not None
    assert c.hero.name  # any non-empty name
    assert c.state.current_stun == c.combat_stats().max_stun


def test_attack_resolves_through_engine_end_to_end():
    """End-to-end: load the character twice, build AttackInput from its own
    Energy Blast view, run RangedAttackAction.resolve() — expect the
    audit trail to carry concrete to_hit / damage / defense lines.

    Uses the to_legacy_combatant pattern (combatant-redesign step 4
    bridge): each HeroCombatant exposes combat_stats() / .state, and
    legacy Combatant has the no-op shim returning self, so the
    engine consumes either uniformly. We feed the engine the legacy
    shape via a minimal attacker / target Combatant built from the
    HeroCombatant's combat_stats().
    """
    from kirby_combat.actions import RangedAttackAction, AttackInput
    from kirby_combat.models import StatBlockCombatant, DiceValues
    from kirby_combat.template import CombatTemplate

    # Ravel carries a dice-bearing Energy Blast; the character used here has
    # to actually have an attack with damage, or the assertions below pass
    # vacuously on a 0-dice power.
    attacker = HeroCombatant.from_hdc(require_authored("Ravel"), id="attacker")
    target = HeroCombatant.from_hdc(require_authored("Ravel"), id="defender")

    s_a = attacker.combat_stats()
    s_b = target.combat_stats()

    # Build a minimal legacy Combatant per side so the existing
    # action+resolution layer (which reads .ocv/.dcv/.pd/.ed/etc.)
    # has the fields it expects. The shim makes both shapes
    # interchangeable in step 4.
    # NOT synthetic: this deliberately builds the flat shape to prove
    # HeroCombatant's stats can be projected into it (the step-4 bridge).
    def _flat(hc, sst):
        return StatBlockCombatant(
            id=hc.id, name=hc.hero.name or hc.id,
            ocv=sst.ocv, dcv=sst.dcv, omcv=sst.omcv, dmcv=sst.dmcv,
            spd=sst.spd, dex=sst.dex, ego=sst.ego, str_=sst.str_,
            con=sst.con, pre=sst.pre, rec=sst.rec,
            pd=sst.pd, ed=sst.ed, rpd=sst.rpd, red=sst.red, md=sst.md,
            power_defense=sst.power_defense, flash_defense=sst.flash_defense,
            max_stun=sst.max_stun, max_body=sst.max_body, max_end=sst.max_end,
            current_stun=hc.state.current_stun,
            current_body=hc.state.current_body,
            current_end=hc.state.current_end,
        )

    a = _flat(attacker, s_a)
    t = _flat(target, s_b)

    # Find an attack power on attacker via attack_view
    atk = None
    for p in attacker.hero.powers:
        x = (getattr(p, "xmlid", None) or "").upper()
        if x in {"ENERGYBLAST", "RKA", "HKA"}:
            try:
                atk = attacker.attack_view(p.xmlid)
                break
            except ValueError:
                continue

    assert atk is not None, "the character should have at least one dice attack"
    assert atk.damage_dice >= 1

    # Deterministic dice — produces a known result
    dv = DiceValues(
        to_hit=[3, 3, 3],   # 3+3+3 = 9, mid roll
        damage=[3] * atk.damage_dice,
        hit_location=[], stun_multiplier=[], knockback=[],
    )
    ai = AttackInput(
        attacker=a, target=t, power=atk,
        distance_m=10.0, aim=None, dice=dv,
        ocv_modifier=0, dcv_modifier=0, dc_modifier=0,
    )
    template = CombatTemplate(name="kirby-combat-fixture-test")
    result = RangedAttackAction().resolve(ai, template)

    # Audit trail should have at least the to_hit lines and SOME
    # damage line. We're not pinning hit/miss because that depends
    # on the character's actual OCV/DCV, which can change with HD fixes.
    assert len(result.audit_trail) > 0
    assert any("OCV" in line for line in result.audit_trail)
    assert any("DCV" in line for line in result.audit_trail)
    # If hit, audit should mention damage; if miss, it should mention miss.
    if result.hit:
        assert result.stun_dealt >= 0
        assert any("STUN" in line or "damage" in line.lower()
                   for line in result.audit_trail)
    else:
        assert any("MISS" in line.upper() for line in result.audit_trail)


# ---------------------------------------------------------------------------
# Int boundary — the cost engine's characteristic_value() returns float
# (canon HDC/build-doc imports yield whole-valued floats like OCV=4.0).
# _compute_stats_from_hero is the seam that must coerce to int so the
# resolution layer never sees float stats (float PRE // 5 dice counts
# used to TypeError in roll_dice; float margins used to ValueError on
# the {margin:+d} audit format).
# ---------------------------------------------------------------------------


def test_compute_stats_coerces_engine_floats_to_int():
    """A hero whose characteristic_value() returns floats (the real
    engine's behaviour) must produce all-int HeroCombatStats."""
    from kirby_combat.hero_view import _compute_stats_from_hero

    class _FloatHero:
        name = "Floaty"
        powers: list = []

        def characteristic_value(self, xmlid: str) -> float:
            return {
                "OCV": 8.0, "DCV": 7.0, "OMCV": 3.0, "DMCV": 3.0,
                "SPD": 5.0, "DEX": 23.0, "EGO": 14.0, "STR": 60.0,
                "CON": 28.0, "PRE": 20.0, "REC": 12.0,
                "PD": 25.0, "ED": 20.0,
                "STUN": 50.0, "BODY": 15.0, "END": 60.0,
            }.get(xmlid, 0.0)

    stats = _compute_stats_from_hero(_FloatHero())
    for field_name in (
        "ocv", "dcv", "omcv", "dmcv", "spd", "dex", "ego", "str_",
        "con", "pre", "rec", "pd", "ed", "rpd", "red", "md",
        "power_defense", "flash_defense", "max_stun", "max_body",
        "max_end",
    ):
        value = getattr(stats, field_name)
        assert type(value) is int, f"{field_name} leaked as {type(value)}"
    # The downstream computations that crashed pre-fix now yield ints:
    assert stats.pre // 5 == 4 and type(stats.pre // 5) is int
    assert stats.str_ // 5 == 12 and type(stats.str_ // 5) is int


def test_canon_hdc_combatant_stats_are_int_and_rollable():
    """End-to-end: a real HDC-loaded combatant feeds integer dice
    counts to RandomRoller (PRE dice, STR strike dice)."""
    pytest.importorskip("kirby_cost")
    require_authored("Bokor")

    from kirby_combat.dice import RandomRoller
    from kirby_combat.pre_attacks.presence import base_pre_dice

    c = HeroCombatant.from_hdc(require_authored("Bokor"))
    stats = c.combat_stats()
    assert type(stats.ocv) is int and type(stats.pre) is int

    roller = RandomRoller(seed=11)
    pre_dice = base_pre_dice(c)
    assert type(pre_dice) is int
    assert len(roller.roll_dice(pre_dice)) == pre_dice

    strike = c.str_strike_view()
    assert type(strike.damage_dice) is int
    assert len(roller.roll_dice(strike.damage_dice)) == strike.damage_dice
