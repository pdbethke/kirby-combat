"""Which hand holds each weapon, stated at the start of the fight.

6E2 p.113: an Impairing wound to the hands, arms or shoulders is "-3 OCV for
any attacks using that arm" --- so the engine has to know which arm a gun is
in. RULINGS (Peter, 2026-11-27): grips are stated per weapon at the start of
the fight, never assumed; a gun its owner picks back up goes to a free hand,
the right if both are free; a gun bought Two-Handed (HD's REQUIREDHANDS
"TWO", 6E1 Limitations) needs both.
"""
from __future__ import annotations

import pytest

from tests.conftest_grips import gun, gunman, session_of, weapon_id
from kirby_combat.template import RAW_HEROIC
from kirby_combat.grips import (
    BOTH, LEFT, RIGHT, Grip, GripsMissing, GripsWrong, grip_of, hands_needed,
    state_grips,
)


@pytest.fixture(autouse=True)
def _template_needed():
    from tests.corpus import require_template
    require_template()


@pytest.fixture
def two_gun_session():
    doc = gunman("doc", gun("shotgun", "Coach Gun"), gun("colt", "Revolver"))
    return session_of(doc, template=RAW_HEROIC), doc


@pytest.fixture
def rifle_session():
    tom = gunman("tom", gun("rifle", "Rifle", two_handed=True))
    return session_of(tom, template=RAW_HEROIC), tom


def test_a_two_handed_gun_needs_both_hands(rifle_session, two_gun_session):
    """Read off the build's own REQUIREDHANDS, as HD wrote it."""
    (_, tom), (_, doc) = rifle_session, two_gun_session
    assert hands_needed(tom.hero.powers[0]) == 2
    assert hands_needed(doc.hero.powers[0]) == 1


def test_a_grip_is_read_back_off_the_log(two_gun_session):
    session, doc = two_gun_session
    shotgun, colt = weapon_id(doc, "Coach Gun"), weapon_id(doc, "Revolver")
    session = state_grips(session, doc.id, [Grip(shotgun, RIGHT), Grip(colt, LEFT)])
    assert grip_of(session, doc.id, shotgun) == RIGHT
    assert grip_of(session, doc.id, colt) == LEFT


def test_no_grip_stated_is_refused(two_gun_session):
    session, doc = two_gun_session
    shotgun, colt = weapon_id(doc, "Coach Gun"), weapon_id(doc, "Revolver")
    session = state_grips(session, doc.id, [Grip(shotgun, RIGHT)])
    with pytest.raises(GripsMissing, match=colt):
        grip_of(session, doc.id, colt)


def test_two_guns_in_one_hand_are_refused(two_gun_session):
    session, doc = two_gun_session
    shotgun, colt = weapon_id(doc, "Coach Gun"), weapon_id(doc, "Revolver")
    with pytest.raises(GripsWrong, match="right"):
        state_grips(session, doc.id, [Grip(shotgun, RIGHT), Grip(colt, RIGHT)])


def test_a_rifle_in_one_hand_is_refused(rifle_session):
    session, tom = rifle_session
    rifle = weapon_id(tom, "Rifle")
    with pytest.raises(GripsWrong, match="two hands"):
        state_grips(session, tom.id, [Grip(rifle, RIGHT)])
    assert grip_of(state_grips(session, tom.id, [Grip(rifle, BOTH)]),
                   tom.id, rifle) == BOTH


def test_a_gun_picked_back_up_goes_to_a_free_hand(two_gun_session):
    """Knocked out of his right hand while his left holds the Colt, it
    comes back to the right: the only free hand. Out of his hand it has no
    grip at all."""
    from kirby_combat.weapons import DISARMED, PICKED_UP, find_weapon, move_weapon

    session, doc = two_gun_session
    shotgun, colt = weapon_id(doc, "Coach Gun"), weapon_id(doc, "Revolver")
    session = state_grips(session, doc.id, [Grip(shotgun, RIGHT), Grip(colt, LEFT)])
    gun_ = find_weapon(session, doc.id, shotgun)
    session = move_weapon(session, gun_, by_id="mark", cause=DISARMED,
                          holder_id=None, position=None)
    assert grip_of(session, doc.id, shotgun) is None
    session = move_weapon(session, gun_, by_id=doc.id, cause=PICKED_UP,
                          holder_id=doc.id, position=None)
    assert grip_of(session, doc.id, shotgun) == RIGHT


def test_with_both_hands_free_it_goes_to_the_right(two_gun_session):
    from kirby_combat.weapons import DISARMED, PICKED_UP, find_weapon, move_weapon

    session, doc = two_gun_session
    shotgun, colt = weapon_id(doc, "Coach Gun"), weapon_id(doc, "Revolver")
    session = state_grips(session, doc.id, [Grip(shotgun, LEFT), Grip(colt, RIGHT)])
    for w in (shotgun, colt):
        session = move_weapon(session, find_weapon(session, doc.id, w), by_id="mark",
                              cause=DISARMED, holder_id=None, position=None)
    session = move_weapon(session, find_weapon(session, doc.id, shotgun), by_id=doc.id,
                          cause=PICKED_UP, holder_id=doc.id, position=None)
    assert grip_of(session, doc.id, shotgun) == RIGHT
