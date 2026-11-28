"""The page says what the man is carrying, and where.

A model seat at the O.K. Corral (2026-11-28) answered an Abort as "Ike is
healthy and armed" with no weapon on Ike's sheet, past a doctrine line that
said "he has nothing to shoot back with". The page listed his stats, his
complications and the ground, and never once what was in his hands --- so
whether he was armed was the reader's guess. The grips (`grips`) and his
attacks are on the fight; this says them.
"""
from __future__ import annotations

import pytest

from tests.conftest_grips import gun, gunman, session_of, weapon_id
from kirby_combat.grips import BOTH, HOLSTERED, Grip, state_grips
from kirby_combat.loop.run import _situation_for
from kirby_combat.side import Side
from kirby_combat.template import RAW_HEROIC


@pytest.fixture(autouse=True)
def _template_needed():
    from tests.corpus import require_template
    require_template()


def _page(session, cid):
    return _situation_for(session, cid).brief().render()


def _foe():
    from fixtures.synthetic_hero import synthetic_combatant
    return synthetic_combatant(id="foe", name="Foe", spd=2, side=Side.named("b"))


def test_a_shotgun_in_both_hands_and_a_colt_holstered():
    doc = gunman("doc", gun("sg", "Shotgun", two_handed=True), gun("colt", "Colt"))
    session = state_grips(session_of(doc, _foe(), template=RAW_HEROIC), "doc",
                          [Grip(weapon_id(doc, "Shotgun"), BOTH),
                           Grip(weapon_id(doc, "Colt"), HOLSTERED)])
    page = _page(session, "doc")
    assert "In hand: Shotgun (both hands). Holstered: Colt." in page, page


def test_a_man_with_no_weapon_is_told_so():
    ike = gunman("ike")
    page = _page(session_of(ike, _foe(), template=RAW_HEROIC), "ike")
    assert "In hand: nothing. You carry no weapon." in page, page


def test_weapons_with_no_stated_grips_are_named():
    """A fight that never said where anything is: name what he has."""
    man = gunman("man", gun("colt", "Colt"))
    page = _page(session_of(man, _foe(), template=RAW_HEROIC), "man")
    assert "Weapons: Colt." in page, page
