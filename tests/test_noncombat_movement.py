"""Noncombat movement is double combat movement, and each Improved
Noncombat level doubles it again.

6E1 p.157: "his Noncombat Movement rate is double his Combat Movement
rate"; p.159: "For every +5 Character Points, a character's rate of
Noncombat Movement with a single mode of movement doubles"; p.302:
"Teleportation has a Noncombat Movement mode like other Movement Powers".
The view had x4 for running, leaping, flight and swimming and x1 for
teleportation and tunneling, from a table nobody cited, and read no
Improved Noncombat at all.
"""
from __future__ import annotations

import pytest

from kirby_combat.hero_view import noncombat_multiple
from tests.corpus import require_template

_CHARS = [{"xmlid": x, "levels": 0} for x in (
    "STR", "DEX", "CON", "BODY", "STUN", "END", "SPD", "PD", "ED", "REC", "OCV", "DCV")]


@pytest.mark.parametrize("levels, multiple", [
    (0, 2), (1, 4), (2, 8), (3, 16), (4, 32), (5, 64), (6, 125), (7, 250)])
def test_the_doubling_steps(levels, multiple):
    """x125, not x128, at six levels: 6E1 p.450's doubling table, and what
    Hero Designer writes ("x125 Noncombat")."""
    assert noncombat_multiple(levels) == multiple


def test_every_mode_doubles_and_improved_noncombat_doubles_again():
    from kirby_cost.io.build_json import build_from_json

    from kirby_combat.hero_view import HeroCombatant

    require_template()
    hero = build_from_json({
        "name": "Mover", "template": "Main6E",
        "base_points": 400, "disad_points": 75, "experience": 0,
        "characteristics": _CHARS,
        "powers": [
            {"id": "F", "xmlid": "FLIGHT", "levels": 20,
             "adders": [{"id": "a", "xmlid": "IMPROVEDNONCOMBAT", "levels": 2}]},
            {"id": "T", "xmlid": "TELEPORTATION", "levels": 10},
        ],
        "skills": [], "perks": [], "talents": [], "disadvantages": [],
    })
    caps = {c.mode: c for c in HeroCombatant.from_build(hero, id="m").movement_view()}
    assert caps["running"].noncombat_m == 24.0          # the free 12m, x2
    assert caps["flight"].noncombat_m == 160.0          # 20m, x8
    assert caps["teleportation"].noncombat_m == 20.0    # 10m, x2
