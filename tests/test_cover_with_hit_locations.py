"""Behind Cover with Hit Locations costs no OCV (6E2 p.45).

"If the campaign uses the optional Hit Location Table, Behind Cover works
differently. ... Once the GM determines what's Behind Cover, combat occurs
normally. If an attack hits the Behind Cover character, roll the Hit
Location. If the Hit Location rolled is Behind Cover, the attack strikes
the cover instead." The engine charged both --- the table's OCV penalty
and the blocked location rolls --- and at the Corral (2026-11-27) the
Cowboys hit 4 shots in 26, every one at a man behind a barrel.
"""
from __future__ import annotations

from fixtures.synthetic_hero import synthetic_combatant

from kirby_combat.actions.recording import cover_ocv
from kirby_combat.template import RAW_HEROIC, RAW_SUPERHEROIC


def _man():
    return synthetic_combatant(id="m", name="m", ocv=5, dcv=5, spd=3,
                               max_stun=30, max_body=10, max_end=30)


def test_without_hit_locations_half_cover_is_minus_two():
    assert cover_ocv(2, template=RAW_SUPERHEROIC, target=_man()) == -2


def test_with_hit_locations_cover_costs_no_ocv():
    assert cover_ocv(2, template=RAW_HEROIC, target=_man()) == 0
    assert cover_ocv(4, template=RAW_HEROIC, target=_man()) == 0
