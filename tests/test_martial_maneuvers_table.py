"""Martial Maneuvers data table — per 6E2 p93 §STANDARD MARTIAL MANEUVERS.

Verified against Codex (throwback tenant) on 2026-04-25.
"""
from __future__ import annotations

from kirby_combat.tables import MARTIAL_MANEUVERS, MartialManeuver


_VALID_PHASES = {"half", "full", "none"}


def test_all_maneuvers_have_valid_phase():
    for key, m in MARTIAL_MANEUVERS.items():
        assert m.phase in _VALID_PHASES, (
            f"maneuver {key!r} has invalid phase {m.phase!r}"
        )


def test_all_maneuvers_have_non_null_name():
    for key, m in MARTIAL_MANEUVERS.items():
        assert isinstance(m.name, str) and m.name.strip(), (
            f"maneuver {key!r} missing a display name"
        )


def test_martial_strike_is_plus_2_dc_plus_2_dcv():
    """Per 6E2 p93: Martial Strike = +0 OCV, +2 DCV, STR +2d6 (i.e. +2 DCs)."""
    m = MARTIAL_MANEUVERS["martial_strike"]
    assert m.ocv == 0
    assert m.dcv == 2
    assert m.dc_bonus == 2
    assert m.phase == "half"


def test_maneuver_count_matches_6e_rulebook():
    """6E2 p93 lists 14 standard maneuvers + 2 elements (+1 DC, Weapon Element).

    Total = 16 entries. The earlier plan estimated 18; Codex confirms 14+2.
    """
    assert len(MARTIAL_MANEUVERS) == 16


def test_martial_block_is_plus_2_ocv_plus_2_dcv():
    """Spot check: Martial Block per 6E2 p93 (Block, Abort)."""
    m = MARTIAL_MANEUVERS["martial_block"]
    assert m.ocv == 2
    assert m.dcv == 2
    assert "Block" in m.notes


def test_martial_dodge_has_no_ocv_modifier_dash():
    """Dodge has '-' in OCV (no opposed roll). Encoded as 0."""
    m = MARTIAL_MANEUVERS["martial_dodge"]
    assert m.ocv == 0
    assert m.dcv == 5


def test_killing_strike_marked_via_notes():
    m = MARTIAL_MANEUVERS["killing_strike"]
    assert "HKA" in m.notes


def test_offensive_strike_is_plus_4_dc():
    """Offensive Strike: -2 OCV, +1 DCV, STR +4d6 = +4 DCs per 6E2 p93."""
    m = MARTIAL_MANEUVERS["offensive_strike"]
    assert m.ocv == -2
    assert m.dcv == 1
    assert m.dc_bonus == 4


def test_dataclass_is_frozen():
    m = MARTIAL_MANEUVERS["martial_strike"]
    try:
        m.dc_bonus = 99    # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("MartialManeuver should be frozen")
