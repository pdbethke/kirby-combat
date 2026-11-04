"""Which defences answer which threat, and no DCV defence against an area.

6E1 p.321: an area is rolled against the target point (DCV 3), so the
defender's DCV, and anything that adds to it, plays no part.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from shaped import armed, encounter_on, scene_with, shaped_blast

from kirby_combat.defences import (
    NON_THREAT_KINDS, Defence, _THREAT_KINDS, answers_to, is_hth, threatens_a_man,
)
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.reactions import reaction_menu
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


def _view(**kw):
    return SimpleNamespace(**{"area": None, "is_ranged": True, "range_m": 100, **kw})


def _area(shape_name):
    from kirby_combat.power_modifiers import AreaShape

    return SimpleNamespace(shape=AreaShape[shape_name], size_m=2.0)


AREA = _view(area=_area("RADIUS"))


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
    assert answers_to(_view(), kind="darkness_zone") == {Defence.MOVE_OUT}


def test_an_unclassified_kind_raises_naming_it():
    with pytest.raises(ValueError, match="wibble"):
        answers_to(_view(), kind="wibble")


def _enc(area, shape=None):
    from kirby_combat.power_modifiers import AreaShape, AreaSpec, AreaTargeting

    blast = shaped_blast("blast", 8)
    if area:
        blast = replace(blast, area=AreaSpec(
            shape=shape or AreaShape.RADIUS, size_m=2.0, targeting=AreaTargeting.STANDARD,
            explosion=False, personal_immunity=False, width_m=2.0,
            height_m=2.0, thin_cone=False, unbuilt=()))
    return encounter_on(
        scene_with({"shooter": (0, 0, 0), "mark": (5, 0, 0)}),
        armed("shooter", blast, side=VILLAINS, dex=30),
        armed("mark", None, side=HEROES)), blast


def _menu(area, *, kind="attack", scene=True, shape=None):
    enc, blast = _enc(area, shape)
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
    # Dive for Cover is what answers it (6E2 p.87; tests/loop/test_dive_for_cover.py).
    assert kinds == ["no_abort", "dive_for_cover"]


def _surface_view():
    return _view(area=_area("SURFACE"))


def test_a_ranged_surface_is_answered_as_a_single_target_attack():
    """6E1 p.323: a Surface laid on a man is rolled against his own DCV
    (`standing_areas.resolve_surface_use`), not the point's DCV 3, so Dodge
    acts on it and the spacing answers of an area do not."""
    got = answers_to(_surface_view(), kind="attack")
    assert got == answers_to(_view(), kind="attack")
    assert Defence.DODGE in got and Defence.SPACING not in got


def test_dodge_is_offered_against_a_ranged_surface():
    from kirby_combat.power_modifiers import AreaShape

    kinds = [a.kind for a in _menu(True, shape=AreaShape.SURFACE)]
    assert kinds == ["no_abort", "dodge"]


def test_no_map_area_offers_only_none():
    assert [a.kind for a in _menu(True, scene=False)] == ["no_abort"]


def test_an_area_autofire_is_an_area_at_the_menu():
    """Spray along a line is never offered for an area power (autofire_offers
    skips it); an area burst is kind `autofire` with the area view."""
    assert [a.kind for a in _menu(True, kind="autofire")] == [
        "no_abort", "dive_for_cover"]


def test_every_kind_enumeration_offers_is_classified_exactly_once():
    from kirby_combat.enumeration import ALL_ACTION_KINDS

    assert not (_THREAT_KINDS & NON_THREAT_KINDS)
    for kind in sorted(ALL_ACTION_KINDS):
        assert (kind in _THREAT_KINDS) != (kind in NON_THREAT_KINDS), kind
        # And every threat kind has a row.
        if threatens_a_man(kind):
            assert answers_to(_view(), kind=kind), kind


def test_a_non_threat_kind_has_no_answers_and_says_so():
    assert threatens_a_man("grab") and not threatens_a_man("move")
    with pytest.raises(ValueError, match="threatens_a_man"):
        answers_to(_view(), kind="move")


def test_an_unclassified_kind_fails_threatens_a_man():
    with pytest.raises(ValueError, match="wibble"):
        threatens_a_man("wibble")


def test_haymaker_is_hand_to_hand_in_the_table_and_the_menu():
    assert is_hth("haymaker", _view())
    assert Defence.BLOCK in answers_to(_view(), kind="haymaker")


@pytest.mark.parametrize("kind", ["mind_scan", "telepathy"])
def test_mind_scan_and_telepathy_are_mental_threats(kind):
    """Both roll MCV against the target's DMCV and act on him
    (`loop.resolvers`), so they are threats on the mental row."""
    assert threatens_a_man(kind)
    assert answers_to(_view(), kind=kind) == {Defence.DISTANCE}
