"""HeroCombatant.maneuver_view() builds combat-ready records from a
character's OWN bought martial maneuvers (martial-arts §3, Task 3.2).

Grounded in Cheshire Cat's real loaded maneuvers (engine MARTIALARTS
section). His 7 MANEUVER entries (the loader also emits a blank List
wrapper + the EXTRADC element, which maneuver_view filters out):

  Martial Dodge    ocv='--' dcv='+5'  effect='Dodge, Affects All Attacks, Abort'
  Martial Escape   ocv='+0' dcv='+0'  effect='[STRDC] vs. Grabs'
  Martial Grab     ocv='-1' dcv='-1'  effect='Grab Two Limbs, [STRDC] for holding on'
  Joint Lock/Throw ocv='+1' dcv='+0'  effect='Grab One Limb; [NNDDC]; Target Falls'
  Defensive Block  ocv='+1' dcv='+3'  effect='Block, Abort'
  Defensive Strike ocv='+1' dcv='+3'  effect='[NORMALDC] Strike'
  Martial Throw    ocv='+0' dcv='+1'  effect='[NORMALDC] +v/10, Target Falls'

The fixture HDC lives in the champions-campaign-manager corpus; tests
skip if it isn't present (CI without the workspace).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kirby_combat.hero_view import HeroCombatant, MartialManeuverView

CHESHIRE_HDC = Path(
    "/home/pdbethke/PycharmProjects/Kirby/champions-campaign-manager/resources/"
    "villains/Champions_Villain_Teams_Character_Pack/"
    "Champions Villains 2 6E ƒ/GRAB/CHESHIRE_CAT-CV2.hdc"
)


def _cheshire() -> HeroCombatant:
    if not CHESHIRE_HDC.exists():
        pytest.skip(f"Cheshire HDC fixture not present: {CHESHIRE_HDC}")
    return HeroCombatant.from_hdc(str(CHESHIRE_HDC))


def test_maneuver_view_surfaces_character_maneuvers():
    hc = _cheshire()
    views = hc.maneuver_view()
    names = {v.name for v in views}
    assert "Martial Dodge" in names
    assert any("Throw" in n for n in names)
    assert len(views) >= 6
    # Non-maneuver entries (blank List wrapper, EXTRADC element) are filtered.
    assert "" not in names
    assert not any("Damage Class" in n for n in names)


def test_martial_dodge_is_a_reactive_dodge_with_dcv_bonus():
    hc = _cheshire()
    dodge = next(v for v in hc.maneuver_view() if v.name == "Martial Dodge")
    assert dodge.is_dodge is True
    assert dodge.dcv >= 4          # Martial Dodge is DCV +5 ("--" OCV)
    assert dodge.ocv == 0          # "--" parses to 0
    assert dodge.is_attack is False  # Dodge makes no attack roll


def test_a_throw_maneuver_sets_target_falls():
    hc = _cheshire()
    throw = next(v for v in hc.maneuver_view() if "Throw" in v.name)
    assert throw.target_falls is True
    assert throw.is_attack is True


def test_views_carry_reach_and_hth_flag():
    hc = _cheshire()
    for v in hc.maneuver_view():
        if v.category_is_ranged:
            assert v.reach_m == 0.0
        else:
            assert v.reach_m >= 2.0   # HTH reach (2m + stretching)


def test_block_maneuver_flags_is_block_and_not_attack():
    hc = _cheshire()
    block = next(v for v in hc.maneuver_view() if v.name == "Defensive Block")
    assert block.is_block is True
    assert block.is_attack is False


def test_strike_maneuver_is_an_attack_without_target_falls():
    hc = _cheshire()
    strike = next(v for v in hc.maneuver_view() if v.name == "Defensive Strike")
    assert strike.is_attack is True
    assert strike.target_falls is False
    assert strike.is_block is False
    assert strike.is_dodge is False


def test_hero_with_no_maneuvers_returns_empty_list():
    # A hero whose martial_arts is missing/None must yield [] (robustness).
    class _Bare:
        martial_arts = None
        powers: list = []

    hc = HeroCombatant.__new__(HeroCombatant)
    object.__setattr__(hc, "hero", _Bare())
    assert hc.maneuver_view() == []
