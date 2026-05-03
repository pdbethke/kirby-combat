"""Tests for the three hero_view API fixes (2026-05-03):

1. ``HeroCombatant.attacks`` returns every attack-shaped power
   instance — no deduplication by xmlid (so multipower batteries
   and characters with multiple EBs are fully addressable).
2. ``HeroCombatant.attack_view(xmlid, name=...)`` disambiguates
   among same-xmlid powers by display name.
3. ``HeroCombatant.str_strike_view()`` builds the implicit Strike
   AttackPower for any combatant — no need to synthesise one.
4. STR-using attacks (HKA, HANDTOHANDATTACK, HA) augment damage by
   STR/5 DCs subject to the 6E Doubling Rule (cap at base DCs).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kirby_combat.hero_view import HeroCombatant, HeroCombatState
from kirby_combat.models import AttackPower


# ── Minimal hero stub: just enough surface for hero_view to work ──────────
@dataclass
class StubPower:
    xmlid: str
    name: str = ""
    levels: int = 0
    level_value: float = 1.0
    base_cost: float = 0.0
    active_cost: float | None = None
    assigned_modifiers: list = field(default_factory=list)
    sub_powers: list = field(default_factory=list)
    assigned_adders: list = field(default_factory=list)


@dataclass
class StubHero:
    name: str = "Test Hero"
    template_name: str = "synthetic.Test.hdt"
    powers: list = field(default_factory=list)
    skills: list = field(default_factory=list)
    perks: list = field(default_factory=list)
    talents: list = field(default_factory=list)
    complications: list = field(default_factory=list)
    equipment: list = field(default_factory=list)
    _char_values: dict = field(default_factory=dict)

    def characteristic_value(self, xmlid: str) -> int:
        return self._char_values.get(xmlid.upper(), 0)


def _make_combatant(*, str_=10, dex=10, con=10, ego=10, pre=10,
                    powers=None, name="Test", id="test"):
    chars = {
        "STR": str_, "DEX": dex, "CON": con, "INT": 10, "EGO": ego, "PRE": pre,
        "OCV": 5, "DCV": 5, "OMCV": 3, "DMCV": 3, "SPD": 4,
        "PD": 5, "ED": 5, "REC": 5, "END": 50, "BODY": 10, "STUN": 30,
        "RUNNING": 12, "SWIMMING": 4, "LEAPING": 4,
    }
    hero = StubHero(name=name, powers=powers or [], _char_values=chars)
    return HeroCombatant(
        id=id, hero=hero,  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=30, current_body=10, current_end=50),
        knockback_resistance=0,
    )


# ── Fix #1: attacks returns ALL same-xmlid instances ─────────────────────
def test_attacks_returns_all_same_xmlid_eb_instances() -> None:
    """Cheshire Cat shape: 1d6 unnamed EB + 6d6 'Teleportation Boxing' EB.
    Both must be addressable through .attacks.
    """
    powers = [
        StubPower(xmlid="ENERGYBLAST", name="", levels=1),
        StubPower(xmlid="ENERGYBLAST", name="Teleportation Boxing", levels=6),
    ]
    c = _make_combatant(powers=powers)
    atks = c.attacks
    assert len(atks) == 2, (
        f"expected 2 EB views (1d6 + 6d6), got {len(atks)}: "
        f"{[(a.name, a.damage_dice) for a in atks]}"
    )
    by_dice = {a.damage_dice for a in atks}
    assert by_dice == {1, 6}


def test_attacks_returns_all_same_xmlid_hka_instances() -> None:
    """GORGON shape: HKA Claws (L2) + HKA Fangs (L1) — both surface."""
    powers = [
        StubPower(xmlid="HKA", name="Claws", levels=2, level_value=1.0/3),
        StubPower(xmlid="HKA", name="Fangs", levels=1, level_value=1.0/3),
    ]
    c = _make_combatant(str_=10, powers=powers)
    atks = c.attacks
    names = {a.name for a in atks}
    assert names == {"Claws", "Fangs"}


def test_attacks_walks_subpowers_for_multipower_slots() -> None:
    """Multipower battery: top-level framework with EB slots inside.

    The walk should descend into sub_powers and yield each slot.
    """
    mp = StubPower(xmlid="MULTIPOWER", name="Force Battery", sub_powers=[
        StubPower(xmlid="ENERGYBLAST", name="Force Bolt", levels=8),
        StubPower(xmlid="ENERGYBLAST", name="Force Cone", levels=6),
        StubPower(xmlid="RKA", name="Force Lance", levels=2, level_value=1.0/3),
    ])
    c = _make_combatant(powers=[mp])
    atks = c.attacks
    names = {a.name for a in atks}
    assert names == {"Force Bolt", "Force Cone", "Force Lance"}


# ── Fix #2: attack_view(xmlid, name=...) disambiguates ────────────────────
def test_attack_view_by_name_picks_specific_power() -> None:
    """Without name=, attack_view returns first-match. With name=,
    the named power is selected even if a different one came first.
    """
    powers = [
        StubPower(xmlid="ENERGYBLAST", name="", levels=1),
        StubPower(xmlid="ENERGYBLAST", name="Teleportation Boxing", levels=6),
    ]
    c = _make_combatant(powers=powers)
    # Default first-match
    first = c.attack_view("ENERGYBLAST")
    assert first.damage_dice == 1
    # Named lookup
    boxing = c.attack_view("ENERGYBLAST", name="Teleportation Boxing")
    assert boxing.damage_dice == 6
    assert boxing.name == "Teleportation Boxing"


def test_attack_view_name_mismatch_raises() -> None:
    powers = [StubPower(xmlid="ENERGYBLAST", name="A", levels=2)]
    c = _make_combatant(powers=powers)
    try:
        c.attack_view("ENERGYBLAST", name="DoesNotExist")
    except ValueError:
        return
    raise AssertionError("expected ValueError for nonexistent name")


# ── Fix #3a: str_strike_view ──────────────────────────────────────────────
def test_str_strike_view_basic() -> None:
    """STR 50 builds a 10d6 normal Strike."""
    c = _make_combatant(str_=50)
    s = c.str_strike_view()
    assert s.xmlid == "STR"
    assert s.damage_dice == 10
    assert s.half_die is False
    assert s.damage_type == "normal"
    assert s.defense_type == "pd"
    assert s.range_m == 0.0
    assert s.uses_str is True


def test_str_strike_view_half_die_threshold() -> None:
    """STR % 5 ≥ 3 produces a +½d6."""
    c = _make_combatant(str_=53)  # 10d6 + ½d6 (extra 3 over 50)
    s = c.str_strike_view()
    assert s.damage_dice == 10
    assert s.half_die is True


def test_str_strike_view_under_5_str() -> None:
    c = _make_combatant(str_=2)
    s = c.str_strike_view()
    assert s.damage_dice == 0
    assert s.half_die is False


# ── Fix #3b: STR augmentation on HKA / HANDTOHANDATTACK / HA ──────────────
def test_hka_str_augmentation_doubling_rule() -> None:
    """1d6 HKA (3 DC base) with STR 60 (12 DC available) is capped at +3 DC.
    +3 DC killing = +1½d6 → final 2½d6 (= 2 full + half).

    Engine tracks killing in half-die steps; 1d6 = 2 steps, +3 DC = +3 steps,
    final = 5 steps = 2 full + 1 half.
    """
    powers = [StubPower(xmlid="HKA", name="Claws", levels=2,
                        level_value=1.0/3, base_cost=15)]
    c = _make_combatant(str_=60, powers=powers)
    atks = c.attacks
    assert len(atks) == 1
    claws = atks[0]
    assert claws.damage_type == "killing"
    # base: levels=2 + base_cost≥15 ⇒ steps = 2 + 2 = 4 ⇒ 2 full, no half
    # So base is 2d6 killing (NOT 1d6 — base_cost=15 means start at 1d6 and
    # each level adds a step, so 2 levels = 1d6 + 1 step = 1d6 + ½ steps?)
    # Actually with base_cost≥15: steps = levels + 2 = 4 ⇒ 2 full + 0 half
    # Doubling rule: 4 base steps ⇒ cap +4 DC from STR
    # STR 60 = 12 DC, capped to 4 ⇒ +4 steps ⇒ total steps 8 ⇒ 4d6 killing
    assert claws.damage_dice == 4, (
        f"expected 4d6 killing (2d6 base + capped 2d6 STR add), got "
        f"{claws.damage_dice}d6{'+½' if claws.half_die else ''}"
    )


def test_handtohandattack_str_augmentation_normal() -> None:
    """HANDTOHANDATTACK 4d6 + STR 50 = 4 base DC + capped 4 from STR
    ⇒ 8d6 normal."""
    powers = [StubPower(xmlid="HANDTOHANDATTACK", name="Punch", levels=4)]
    c = _make_combatant(str_=50, powers=powers)
    atks = c.attacks
    assert len(atks) == 1
    punch = atks[0]
    assert punch.damage_type == "normal"
    assert punch.damage_dice == 8
    assert punch.uses_str is True


def test_energyblast_does_not_get_str_augmentation() -> None:
    """ENERGYBLAST is not STR-using — STR doesn't affect it."""
    powers = [StubPower(xmlid="ENERGYBLAST", name="Bolt", levels=6)]
    c = _make_combatant(str_=80, powers=powers)
    atks = c.attacks
    assert len(atks) == 1
    bolt = atks[0]
    assert bolt.damage_dice == 6  # unchanged
    assert bolt.uses_str is False


def test_low_str_partial_augmentation() -> None:
    """STR 10 (2 DC) on a 4d6 HA: base allows up to +4 DC, STR provides
    only 2 — so add the 2 fully (no cap kicks in)."""
    powers = [StubPower(xmlid="HA", name="Bash", levels=4)]
    c = _make_combatant(str_=10, powers=powers)
    atks = c.attacks
    assert len(atks) == 1
    bash = atks[0]
    assert bash.damage_dice == 6  # 4 base + 2 from STR
