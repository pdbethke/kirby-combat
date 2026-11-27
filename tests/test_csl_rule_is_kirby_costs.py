"""Which attacks a Combat Skill Level reaches is kirby-cost's rule (6E1 72).

kirby-cost's workshop limits and this engine's to-hit roll must read one rule,
so the rule lives in `kirby_cost.engine.csl` (lifted from here, kirby-cost
0.9.0) and this engine calls it. Each caller is proven to call it: answer
differently there and the answer here follows.

What stays here is this engine's reading of doubt: kirby-cost answers
UNKNOWN when a level's words cannot say, and a fight reads that as "does not
reach", narrowing as it always has.
"""
from __future__ import annotations

import pytest
from kirby_cost.engine import csl as cost_csl

from kirby_combat import hero_view
from kirby_combat.models import AttackPower, CombatSkillLevel
from kirby_combat.resolution import to_hit


def _fist() -> AttackPower:
    return AttackPower(
        xmlid="HANDTOHANDATTACK", name="Fist", damage_dice=8,
        half_die=False, plus_one=False,
        damage_type="normal", defense_type="pd", range_m=0,
        uses_str=False, str_min=0,
        armor_piercing=0, penetrating=0, increased_stun_mult=0,
        source_id="w2", is_ranged=False, reach_m=2.0,
    )


def test_to_hit_asks_kirby_cost_whether_a_level_reaches(monkeypatch):
    level = CombatSkillLevel(levels=1, applies_to="ocv", breadth="single",
                             named_attacks="with my fist")
    assert to_hit._csl_reaches(level, _fist())
    asked = []

    def no(breadth, named, labels, ranged):
        asked.append((breadth, named, tuple(labels), ranged))
        return cost_csl.Reach.NO
    monkeypatch.setattr(to_hit, "reaches", no)
    assert not to_hit._csl_reaches(level, _fist())
    assert asked == [(cost_csl.Breadth.SINGLE, "with my fist", ("Fist", ""), False)]


@pytest.mark.parametrize("answer, reached", [
    (cost_csl.Reach.YES, True), (cost_csl.Reach.NO, False),
    (cost_csl.Reach.UNKNOWN, False),
])
def test_a_fight_reads_doubt_as_does_not_reach(monkeypatch, answer, reached):
    monkeypatch.setattr(to_hit, "reaches", lambda *a: answer)
    level = CombatSkillLevel(levels=1, applies_to="ocv", breadth="tight",
                             named_attacks="fist")
    assert to_hit._csl_reaches(level, _fist()) is reached


def test_a_hand_built_level_with_no_breadth_still_reaches_everything():
    """A caller handing in a level it has already decided on (breadth "")
    keeps the All Attacks reading this engine has always given it."""
    level = CombatSkillLevel(levels=1, applies_to="ocv", breadth="", named_attacks="")
    assert to_hit._csl_reaches(level, _fist())


def _powerlad():
    from corpus import require_authored, require_template

    require_template()
    return require_authored("PowerLad")


def test_a_builds_breadth_is_kirby_costs_reading(monkeypatch):
    doc = _powerlad()
    monkeypatch.setattr(hero_view, "breadth_of", lambda level: cost_csl.Breadth.RANGED)
    lad = hero_view.HeroCombatant.from_build(doc, id="lad")
    assert [c.breadth for c in lad.csls] == ["ranged"]


def test_a_breadth_kirby_cost_cannot_read_stays_this_engines_narrowest(monkeypatch):
    """Unchanged from before the move: none of HD's six reads as "single",
    which reaches only an attack its words name."""
    doc = _powerlad()
    monkeypatch.setattr(hero_view, "breadth_of", lambda level: None)
    lad = hero_view.HeroCombatant.from_build(doc, id="lad")
    assert [c.breadth for c in lad.csls] == ["single"]


def test_a_builds_named_attacks_are_kirby_costs_reading(monkeypatch):
    doc = _powerlad()
    monkeypatch.setattr(hero_view, "named_text", lambda level: "with my left hook")
    lad = hero_view.HeroCombatant.from_build(doc, id="lad")
    assert [c.named_attacks for c in lad.csls] == ["with my left hook"]
