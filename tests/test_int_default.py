"""`int_` must stay a defaulted field on the two package-boundary shapes.

kirby-api constructs `Vehicle`/`ObjectCombatant` (both `StatBlockCombatant`
subtypes) directly by keyword in entity_service.py, and `HeroCombatStats`
is constructed elsewhere the same way -- neither call site passes `int_`.
A non-defaulted `int_` field raises `TypeError` at both, which would ship
as a breaking patch release against kirby-cost's `pyproject.toml` version.
See `kirby_combat/models.py` and `kirby_combat/hero_view.py` for the
default's rationale (10 -- the HERO baseline for a normal human
characteristic, matching the old `getattr(stats, "int_", ...)` fallback).

Vehicle/ObjectCombatant-specific regressions for the same rule live next
to their own factories: `tests/vehicles/test_vehicle.py::
test_vehicle_constructs_by_keyword_without_int` and `tests/breakables/
test_object_combatant.py::test_object_combatant_constructs_by_keyword_
without_int`.
"""
from __future__ import annotations

from kirby_combat.hero_view import HeroCombatStats
from kirby_combat.models import StatBlockCombatant


def _stat_block_kwargs() -> dict:
    return dict(
        id="c1", name="Cheshire",
        ocv=5, dcv=5, omcv=3, dmcv=3,
        spd=4, dex=20, ego=15,
        str_=15, con=15, pre=15, rec=8,
        pd=8, ed=8, rpd=0, red=0, md=0,
        power_defense=0, flash_defense=0,
        max_stun=30, max_body=12, max_end=30,
        current_stun=30, current_body=12, current_end=30,
        # int_ deliberately omitted -- that's the point of this test.
    )


def test_stat_block_combatant_constructs_without_int():
    c = StatBlockCombatant(**_stat_block_kwargs())
    assert c.int_ == 10


def test_hero_combat_stats_constructs_without_int():
    stats = HeroCombatStats(
        ocv=5, dcv=5, omcv=3, dmcv=3, spd=4,
        dex=20, ego=15, str_=15, con=15, pre=15, rec=8,
        pd=8, ed=8, rpd=0, red=0, md=0,
        power_defense=0, flash_defense=0,
        max_stun=30, max_body=12, max_end=30,
        # int_ deliberately omitted -- that's the point of this test.
    )
    assert stats.int_ == 10
