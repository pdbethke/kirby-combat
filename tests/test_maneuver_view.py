"""Martial maneuver view.

Two kinds of test live here and they are kept apart deliberately.

The FLAG tests are mechanics: `maneuver_view` derives is_dodge / is_block /
is_attack / target_falls from the maneuver's raw EFFECT string, and that
derivation is what they check. They use synthetic maneuvers so the input is
stated as data — a stub says exactly which effect string produces which flag,
where a character file only says "this build happened to have a Dodge".

The INGESTION test needs a real HD file, and uses an authored character (see
`tests/corpus.py`); it skips when the corpus is not configured.
"""
from __future__ import annotations

import pytest

from kirby_combat.hero_view import HeroCombatant, MartialManeuverView

from tests.corpus import require_authored


class _Maneuver:
    """A martial maneuver shaped as `maneuver_view` reads one."""

    def __init__(self, display: str, effect: str, *, ocv: str = "+0",
                 dcv: str = "+0", category: str = "Hand To Hand",
                 damage_type: int = 0, dc: int = 0, maneuver_id: str = "m1"):
        self.xmlid = "MANEUVER"
        self.display = display
        self.effect = effect
        self.ocv = ocv
        self.dcv = dcv
        self.category = category
        self.damage_type = damage_type
        self.dc = dc
        self.id = maneuver_id
        self.phase = "1/2"
        self.add_str = False


class _StubMartialHero:
    def __init__(self, *maneuvers):
        self.martial_arts = list(maneuvers)
        self.powers: list = []


def _view_of(*maneuvers) -> list[MartialManeuverView]:
    hc = HeroCombatant.__new__(HeroCombatant)
    object.__setattr__(hc, "hero", _StubMartialHero(*maneuvers))
    return hc.maneuver_view()


# --- flag derivation from the EFFECT string ---------------------------------

def test_a_dodge_is_reactive_with_a_dcv_bonus_and_no_attack():
    (dodge,) = _view_of(_Maneuver(
        "Martial Dodge", "Dodge, Affects All Attacks, Abort",
        ocv="--", dcv="+5"))
    assert dodge.is_dodge is True
    assert dodge.is_attack is False   # a Dodge makes no attack roll
    assert dodge.dcv == 5
    assert dodge.ocv == 0             # "--" parses to 0


def test_a_block_flags_is_block_and_not_attack():
    (block,) = _view_of(_Maneuver(
        "Defensive Block", "Block, Abort", ocv="+1", dcv="+3"))
    assert block.is_block is True
    assert block.is_attack is False


def test_a_throw_sets_target_falls_and_is_an_attack():
    (throw,) = _view_of(_Maneuver(
        "Martial Throw", "STR +v/10, Target Falls", ocv="+0", dcv="+1"))
    assert throw.target_falls is True
    assert throw.is_attack is True


def test_a_strike_is_an_attack_with_none_of_the_reactive_flags():
    (strike,) = _view_of(_Maneuver(
        "Defensive Strike", "STR +2d6 Strike", ocv="+1", dcv="+3"))
    assert strike.is_attack is True
    assert strike.target_falls is False
    assert strike.is_block is False
    assert strike.is_dodge is False


def test_the_four_flags_are_not_interchangeable():
    """Each effect string must produce its OWN flag and no other — a swap
    between any two derivations has to be detectable."""
    views = _view_of(
        _Maneuver("D", "Dodge, Abort", maneuver_id="d"),
        _Maneuver("B", "Block, Abort", maneuver_id="b"),
        _Maneuver("T", "STR +v/10, Target Falls", maneuver_id="t"),
        _Maneuver("S", "STR +2d6 Strike", maneuver_id="s"),
    )
    got = {v.name: (v.is_dodge, v.is_block, v.target_falls, v.is_attack)
           for v in views}
    assert got == {
        "D": (True, False, False, False),
        "B": (False, True, False, False),
        "T": (False, False, True, True),
        "S": (False, False, False, True),
    }


def test_ranged_maneuvers_have_no_reach_and_hth_maneuvers_do():
    ranged, hth = _view_of(
        _Maneuver("R", "Strike", category="Ranged", maneuver_id="r"),
        _Maneuver("H", "Strike", category="Hand To Hand", maneuver_id="h"),
    )
    assert ranged.category_is_ranged is True and ranged.reach_m == 0.0
    assert hth.category_is_ranged is False and hth.reach_m >= 2.0


def test_non_maneuver_entries_are_filtered_out():
    """List wrappers and EXTRADC elements share the section but are not
    maneuvers; only ``xmlid == "MANEUVER"`` is surfaced."""
    extra = _Maneuver("+2 Damage Class", "", maneuver_id="x")
    extra.xmlid = "EXTRADC"
    views = _view_of(_Maneuver("Martial Strike", "STR +2d6 Strike"), extra)
    names = {v.name for v in views}
    assert names == {"Martial Strike"}


def test_hero_with_no_maneuvers_returns_empty_list():
    # A hero whose martial_arts is missing/None must yield [] (robustness).
    class _Bare:
        martial_arts = None
        powers: list = []

    hc = HeroCombatant.__new__(HeroCombatant)
    object.__setattr__(hc, "hero", _Bare())
    assert hc.maneuver_view() == []


# --- ingestion from a real HD character file --------------------------------

def test_maneuver_view_surfaces_a_real_characters_maneuvers():
    """The real-file half: a character's maneuvers arrive named, typed, and
    with the non-maneuver section entries already filtered out."""
    hc = HeroCombatant.from_hdc(require_authored("Ravel"))
    views = hc.maneuver_view()
    assert views, "the authored character should carry martial maneuvers"
    names = {v.name for v in views}
    assert "" not in names
    assert not any("Damage Class" in n for n in names)
    # This character carries a Block and a Throw; both derive their flags
    # from real EFFECT strings rather than from their display names.
    assert any(v.is_block and not v.is_attack for v in views)
    throw = next(v for v in views if v.target_falls)
    assert throw.is_attack is True
