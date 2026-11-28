"""The page says whether each other man visibly carries a weapon.

A model seat at the O.K. Corral (2026-11-28) opened with Wyatt, Doc and
Morgan all shooting Ike Clanton --- "the closest enemy" --- who had no
weapon, while their side's errand was to disarm the Cowboys. Nothing on the
page said who was armed. An Obvious Accessible Focus is plain to see
(6E1 Focus: Obvious); an Inobvious one is not, and is not named.
"""
from __future__ import annotations

import pytest

from tests.conftest_grips import OAF, gun, gunman, session_of, weapon_id
from kirby_combat.grips import HOLSTERED, RIGHT, Grip, state_grips
from kirby_combat.loop.run import _situation_for
from kirby_combat.template import RAW_HEROIC

IAF = {"xmlid": "FOCUS", "option_id": "IAF", "base_cost": -0.5}


@pytest.fixture(autouse=True)
def _template_needed():
    from tests.corpus import require_template
    require_template()


def _enemy_block(page: str, name: str) -> str:
    lines = page.split("Enemies:", 1)[1].splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(f"  {name} "))
    block = [lines[start]]
    for l in lines[start + 1:]:
        if not l.startswith("    "):
            break
        block.append(l)
    return "\n".join(block)


def test_an_armed_man_and_an_unarmed_one():
    wyatt = gunman("wyatt", gun("colt", "Colt"), side="law")
    frank = gunman("frank", gun("colt", "Colt"), gun("rifle", "Rifle"), side="cow")
    ike = gunman("ike", side="cow")
    session = session_of(wyatt, frank, ike, template=RAW_HEROIC)
    session = state_grips(session, "frank", [Grip(weapon_id(frank, "Colt"), RIGHT),
                                             Grip(weapon_id(frank, "Rifle"), HOLSTERED)])
    page = _situation_for(session, "wyatt").brief().render()
    assert "carries: Colt (in hand), Rifle (holstered)" in _enemy_block(page, "frank"), page
    assert "no weapon in sight" in _enemy_block(page, "ike"), page


def test_an_inobvious_weapon_is_not_seen():
    hidden = {**gun("d", "Derringer"), "modifiers": [IAF]}
    wyatt = gunman("wyatt", gun("colt", "Colt"), side="law")
    gambler = gunman("gambler", hidden, side="cow")
    page = _situation_for(session_of(wyatt, gambler, template=RAW_HEROIC), "wyatt").brief().render()
    block = _enemy_block(page, "gambler")
    assert "Derringer" not in block and "no weapon in sight" in block, page
