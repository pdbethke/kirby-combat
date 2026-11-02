"""Which defences answer which threat, and no DCV defence against an area.

6E1 p.321: an area is rolled against the target point (DCV 3), so the
defender's DCV, and anything that adds to it, plays no part.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from shaped import armed, encounter_on, scene_with, shaped_blast

from kirby_combat.defences import Defence, answers_to
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.reactions import reaction_menu
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


def _view(**kw):
    return SimpleNamespace(**{"area": None, "is_ranged": True, "range_m": 100, **kw})


AREA = _view(area=object())


def test_presence_attack_has_no_answer():
    assert answers_to(_view(), kind="presence_attack") == {Defence.NONE}


def test_mental_blast_is_not_dodged():
    got = answers_to(_view(), kind="mental_blast")
    assert Defence.DODGE not in got and Defence.BLOCK not in got
    assert got == {Defence.DISTANCE}


def test_mental_with_no_range_has_no_answer():
    assert answers_to(_view(is_ranged=False, range_m=0),
                      kind="mental_blast") == {Defence.NONE}


def test_single_target_blast_row():
    assert answers_to(_view(), kind="attack") == {
        Defence.DODGE, Defence.DIVE_FOR_COVER, Defence.COVER, Defence.DISTANCE}


def test_block_only_for_hand_to_hand():
    assert Defence.BLOCK in answers_to(_view(is_ranged=False, range_m=0), kind="attack")
    assert Defence.BLOCK in answers_to(_view(), kind="strike")


def test_area_blast_drops_dodge_and_block():
    got = answers_to(AREA, kind="attack")
    assert {Defence.DIVE_FOR_COVER, Defence.SPACING} <= got
    assert Defence.DODGE not in got and Defence.BLOCK not in got


def test_area_flash_is_union_minus_dcv():
    got = answers_to(AREA, kind="flash")
    assert {Defence.COVER, Defence.DISTANCE, Defence.DIVE_FOR_COVER} <= got
    assert Defence.DODGE not in got


def test_darkness_is_answered_by_moving_out():
    assert answers_to(_view(), kind="darkness") == {Defence.MOVE_OUT}


def test_an_unclassified_kind_raises_naming_it():
    with pytest.raises(ValueError, match="wibble"):
        answers_to(_view(), kind="wibble")


def _enc(area):
    blast = shaped_blast("blast", 8)
    if area:
        blast = replace(blast, area=object())
    return encounter_on(
        scene_with({"shooter": (0, 0, 0), "mark": (5, 0, 0)}),
        armed("shooter", blast, side=VILLAINS, dex=30),
        armed("mark", None, side=HEROES)), blast


def _menu(area, *, kind="attack", scene=True):
    enc, blast = _enc(area)
    s = enc.sessions[0]
    if not scene:
        s = replace(s, scene=None)
    incoming = LegalAction(action_id="a", kind=kind, target_id="mark",
                           power_xmlid=blast.xmlid, power_name="blast",
                           summary="", _attack_view=blast)
    return reaction_menu(s, s.combatants["shooter"], incoming, "mark")


def test_single_target_still_offers_dodge():
    assert "dodge" in [a.kind for a in _menu(False)]


def test_no_dodge_offered_against_an_area_attack():
    kinds = [a.kind for a in _menu(True)]
    assert "dodge" not in kinds and "block" not in kinds
    assert "roll_with_punch" not in kinds


def test_no_map_area_offers_only_none():
    assert [a.kind for a in _menu(True, scene=False)] == ["no_abort"]


def test_an_area_autofire_is_an_area_at_the_menu():
    """Spray along a line is never offered for an area power (autofire_offers
    skips it); an area burst is kind `autofire` with the area view."""
    assert [a.kind for a in _menu(True, kind="autofire")] == ["no_abort"]
