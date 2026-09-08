"""Resistant Protection is defense you BOUGHT, not defense you promoted.

Power Lad carries "Body Like Iron" — Resistant Protection 45 points, split
25 PD / 20 ED — and walked into the O.K. Corral reading **rPD 2**, which
is his bare characteristic PD. Sixty-nine active points contributed
nothing, to either column. PeterB, 2026-09-08: *"his rpd will resist all
bullet fire"* — and it should: a Colt Peacemaker is RKA 2d6-1.

Two defects stacked, and the second ate the first.

1. `_compute_stats_from_hero` guessed the split half-and-half, and said
   so: "Without per-adder parsing we assume the levels split
   half-and-half." 45 became 23/22 rather than the build's own 25/20. It
   is not an adder — `ForceField.XML_ATTRS` reads PDLEVELS/EDLEVELS off
   the element, and the build doc carries them since today.
2. Then `final_rpd = min(rpd + naked_resistant["PD"], base_pd)` threw the
   guess away, because `base_pd` is his characteristic PD of 2.

THE BOOK, 6E2 p.105: "A character's main form of Normal Defense are his
natural PD and ED. These can be SUPPLEMENTED by defenses bought as Powers
(for example, Limited forms of PD and ED, or Resistant Protection)." The
worked example adds leather armor PD 3 on top of natural PD 4 for 7 — the
armor is not capped at 4.

The cap is right for the OTHER construction, and that is why it was
there: the Ogre example on the same page has "PD 40, but only 5 of it is
Resistant", which is natural PD promoted by the Resistant Advantage. You
cannot promote more PD than you own. That cap got applied to both.
"""
from __future__ import annotations

import pytest

from tests.corpus import require_template
from kirby_cost.io.build_json import build_from_json

from kirby_combat.hero_view import HeroCombatant

BASE = {
    "name": "Brick", "template": "builtIn.Superheroic6E.hdt",
    "base_points": 400, "disad_points": 0, "experience": 0,
    "characteristics": [
        # PD 2 is the whole point: the natural defense is tiny and the
        # bought protection is not.
        {"id": "c1", "xmlid": "PD", "levels": 0, "base_cost": 0.0,
         "level_cost": 1.0, "level_value": 1.0, "alias": "PD"},
        {"id": "c2", "xmlid": "ED", "levels": 0, "base_cost": 0.0,
         "level_cost": 1.0, "level_value": 1.0, "alias": "ED"},
    ],
    "powers": [], "skills": [], "perks": [], "talents": [],
    "martial_arts": [], "disadvantages": [], "equipment": [],
}

PROTECTION = {
    "id": "p1", "xmlid": "FORCEFIELD", "levels": 45, "base_cost": 0.0,
    "level_cost": 3.0, "level_value": 2.0, "alias": "Resistant Protection",
    "name": "Body Like Iron", "pd_levels": 25, "ed_levels": 20,
}


@pytest.fixture(autouse=True)
def _needs_a_template():
    """Costing a build needs a .hdt, and neither kirby-cost nor the CI
    runner ships one."""
    require_template()


def _stats(*powers):
    doc = dict(BASE, powers=list(powers))
    return HeroCombatant.from_build(build_from_json(doc)).combat_stats()


def test_resistant_protection_is_not_capped_by_natural_pd():
    """The defect that put Power Lad in a gunfight wearing nothing."""
    assert _stats(PROTECTION).rpd == 25


def test_the_split_comes_from_the_build_not_from_a_guess():
    """25/20, not 23/22. Half of 45 is not what he bought."""
    stats = _stats(PROTECTION)
    assert (stats.rpd, stats.red) == (25, 20)


def test_bought_protection_adds_to_total_defense_too():
    """6E2 p.105's Chiron: natural PD 4 plus leather armor PD 3 is 7, and
    the armor is not capped at 4. Resistant defense protects against
    Normal Damage as well, so it must reach the PD column, not only rPD."""
    stats = _stats(PROTECTION)
    assert stats.pd == 2 + 25, "natural PD plus the protection bought"
    assert stats.ed == 2 + 20


def test_a_character_with_no_protection_is_unchanged():
    """Guards the guard: the ordinary case must not move."""
    stats = _stats()
    assert (stats.pd, stats.rpd) == (2, 0)
