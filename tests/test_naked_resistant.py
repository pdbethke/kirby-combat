"""Tests for NAKEDMODIFIER+RESISTANT propagation to rPD/rED.

The classic HD pattern for a brick: buy NAKEDMODIFIER carrying a
RESISTANT advantage with INPUT="for N PD/N ED". The engine must
parse INPUT, recognise the assigned RESISTANT modifier, and promote
that many points of base PD/ED to rPD/rED on combat_stats.

Real-time-correctness: the derivation runs each call to
combat_stats(), so Drains via state.drains["pd"] correctly reduce
the rPD pool through the cap (rPD ≤ PD).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kirby_combat.hero_view import (
    HeroCombatant, HeroCombatState,
    _parse_input_for_defenses,
)


# ── Minimal hero stub ─────────────────────────────────────────────────────
@dataclass
class StubModifier:
    xmlid: str
    levels: int = 0
    base_cost: float = 0.0


@dataclass
class StubPower:
    xmlid: str
    name: str = ""
    levels: int = 0
    level_value: float = 1.0
    base_cost: float = 0.0
    active_cost: float | None = None
    input_value: str | None = None
    assigned_modifiers: list = field(default_factory=list)
    sub_powers: list = field(default_factory=list)
    assigned_adders: list = field(default_factory=list)


@dataclass
class StubHero:
    name: str = "Test"
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

    def temporal_characteristic(self, xmlid: str, ctx=None) -> int:
        return self.characteristic_value(xmlid)


def _make(*, str_=10, pd=10, ed=10, powers=None) -> HeroCombatant:
    chars = {
        "STR": str_, "DEX": 10, "CON": 10, "INT": 10, "EGO": 10, "PRE": 10,
        "OCV": 5, "DCV": 5, "OMCV": 3, "DMCV": 3, "SPD": 4,
        "PD": pd, "ED": ed, "REC": 5, "END": 50, "BODY": 10, "STUN": 30,
        "RUNNING": 12, "SWIMMING": 4, "LEAPING": 4,
    }
    hero = StubHero(powers=powers or [], _char_values=chars)
    return HeroCombatant(
        id="test", hero=hero,  # type: ignore[arg-type]
        state=HeroCombatState(current_stun=30, current_body=10, current_end=50),
        knockback_resistance=0,
    )


# ── INPUT-parsing helper ──────────────────────────────────────────────────
def test_parse_input_for_defenses_pd_ed_split() -> None:
    assert _parse_input_for_defenses("for 45 PD/45 ED") == {"PD": 45, "ED": 45}


def test_parse_input_for_defenses_single() -> None:
    assert _parse_input_for_defenses("for 30 ED") == {"ED": 30}


def test_parse_input_for_defenses_mental_def() -> None:
    assert _parse_input_for_defenses("for 20 Mental Defense") == {"MD": 20}


def test_parse_input_for_defenses_blank() -> None:
    assert _parse_input_for_defenses(None) == {}
    assert _parse_input_for_defenses("") == {}
    assert _parse_input_for_defenses("for STR 30") == {}  # no defense match


# ── Naked-mod-resistant promotion ─────────────────────────────────────────
def test_naked_resistant_promotes_pd_to_rpd() -> None:
    """GRANITEMAN-shape: 45 PD characteristic + NAKEDMODIFIER L90 RESISTANT
    INPUT='for 45 PD/45 ED' → rPD = 45, rED = 45.
    """
    powers = [
        StubPower(
            xmlid="NAKEDMODIFIER", name="Tough As Granite", levels=90,
            input_value="for 45 PD/45 ED",
            assigned_modifiers=[StubModifier(xmlid="RESISTANT")],
        ),
    ]
    c = _make(pd=45, ed=45, powers=powers)
    s = c.combat_stats()
    assert s.pd == 45
    assert s.ed == 45
    assert s.rpd == 45
    assert s.red == 45


def test_naked_resistant_capped_at_pd_total() -> None:
    """If the NAKEDMODIFIER claims more PD than the character has, rPD
    is capped at the available PD (the doubling rule analog — can't
    promote more than you've got)."""
    powers = [
        StubPower(
            xmlid="NAKEDMODIFIER", name="Overzealous", levels=200,
            input_value="for 100 PD",
            assigned_modifiers=[StubModifier(xmlid="RESISTANT")],
        ),
    ]
    c = _make(pd=20, powers=powers)
    s = c.combat_stats()
    assert s.pd == 20
    assert s.rpd == 20  # capped


def test_naked_resistant_without_resistant_modifier_does_nothing() -> None:
    """A NAKEDMODIFIER without a RESISTANT child is ignored for rPD —
    e.g. GRANITEMAN's first 'Tough As Granite' carries HARDENED only."""
    powers = [
        StubPower(
            xmlid="NAKEDMODIFIER", name="Just Hardened", levels=90,
            input_value="for 45 PD/45 ED",
            assigned_modifiers=[StubModifier(xmlid="HARDENED")],
        ),
    ]
    c = _make(pd=45, ed=45, powers=powers)
    s = c.combat_stats()
    assert s.rpd == 0
    assert s.red == 0


def test_resistant_advantage_on_bare_pd_power_row() -> None:
    """A PD-power row carrying RESISTANT in its assigned_modifiers
    produces rPD equal to its levels (e.g. 'Force Wall +10 PD,
    Resistant')."""
    powers = [
        StubPower(
            xmlid="PD", name="Force Wall", levels=10,
            assigned_modifiers=[StubModifier(xmlid="RESISTANT")],
        ),
    ]
    c = _make(pd=10, powers=powers)
    s = c.combat_stats()
    # Total PD = 10 char + 10 power = 20; rPD = 10 (just the power)
    assert s.pd == 20
    assert s.rpd == 10


def test_drain_on_pd_caps_rpd_real_time() -> None:
    """rPD is capped at current PD. A Drain on PD reduces rPD too —
    not by direct drain, but because the cap pulls down dynamically.
    This is the property that makes the naked-mod fix real-time-safe.
    """
    powers = [
        StubPower(
            xmlid="NAKEDMODIFIER", name="Tough As Granite", levels=90,
            input_value="for 45 PD",
            assigned_modifiers=[StubModifier(xmlid="RESISTANT")],
        ),
    ]
    c = _make(pd=45, powers=powers)
    # Drain 20 PD via state.drains
    c.state.drains["pd"] = 20
    s = c.combat_stats()
    assert s.pd == 25            # 45 − 20
    assert s.rpd == 25           # capped at PD


def test_aid_on_rpd_persists_through_compute() -> None:
    """An Aid on rPD adds to the derived value via state.aids."""
    powers = [
        StubPower(
            xmlid="NAKEDMODIFIER", name="Tough As Granite", levels=90,
            input_value="for 30 PD",
            assigned_modifiers=[StubModifier(xmlid="RESISTANT")],
        ),
    ]
    c = _make(pd=30, powers=powers)
    c.state.aids["rpd"] = 5
    s = c.combat_stats()
    assert s.rpd == 35           # 30 derived + 5 aid (uncapped by current pd=30 since aid is post-compute)
