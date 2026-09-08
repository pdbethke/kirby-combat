"""Complications reach the fight --- they never did.

`Situation` has carried `actor_complications` and `enemy_complications`
since tactics existed, and `bait_enraged` and `exploit_susceptibility`
both read them. NOTHING IN THE LOOP EVER FILLED THEM. A grep of
`kirby_combat/loop/` for either name returns nothing, so in every
loop-driven fight this engine has run, both tactics saw an empty list and
could never fire.

Sixth of the same shape in one week --- computed, correct, delivered
nowhere. `compute_cover_level` had one caller; every tactic's
`narrative_summary` was written for a reader that never saw it;
`PlanStep.target_id` was set by sixteen tactics and read by none;
violence could be resolved and never noticed; `masscombat.UnitMorale` is
a whole subsystem wired to nothing.

WHAT THE DATA ACTUALLY LOOKS LIKE, since three separate probes of mine
guessed the field name wrong before I listed the object: the text of a
Psychological Complication is in **`input`** ("Code vs Killing",
"Overconfidence"), not `input_value` or `name`, both of which are empty.
The severity is in the adders --- HD writes "Intensity Is Total,
Situation Is (Common)" --- which is what 6E2 p.138's table prices at
Moderate +1d6 / Strong +2d6 / Total +3d6.
"""
from __future__ import annotations

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.complications import complications_of
from kirby_combat.side import Side


class _Raw:
    """A complication as the cost engine hands it over."""

    def __init__(self, xmlid, input_text="", alias="", adder_string=""):
        self.xmlid = xmlid
        self.input = input_text
        self.alias = alias
        self.adder_string = adder_string
        self.adders = []
        self.name = ""


def _with(*raw):
    c = fighter("man", side=Side.named("law"))
    c.hero.complications = list(raw)
    return c


def test_a_complication_is_read_off_the_build():
    got = complications_of(_with(_Raw("HUNTED", alias="Hunted")))
    assert [c.xmlid for c in got] == ["HUNTED"]


def test_the_text_comes_from_input_not_from_name():
    """The field that actually holds it. `name` is empty on every
    Psychological Complication in the corpus."""
    got = complications_of(_with(
        _Raw("PSYCHOLOGICALLIMITATION", input_text="Overconfidence",
             alias="Psychological Complication")))
    assert got[0].name == "Overconfidence"


def test_the_text_becomes_searchable_keywords():
    """`Complication.trigger_keywords` is documented as lowercased tokens
    for keyword matching, and is what a tactic asks about."""
    got = complications_of(_with(
        _Raw("PSYCHOLOGICALLIMITATION", input_text="Code vs Killing",
             alias="Psychological Complication")))
    assert "killing" in got[0].trigger_keywords
    assert "code" in got[0].trigger_keywords


def test_the_intensity_survives_as_an_adder():
    """6E2 p.138 prices a psych comp by how strongly it holds ---
    Moderate, Strong, Total. HD writes that in the adder string."""
    got = complications_of(_with(
        _Raw("PSYCHOLOGICALLIMITATION", input_text="Overconfidence",
             adder_string="Intensity Is Total, Situation Is (Common)")))
    assert got[0].adders.get("INTENSITY") == "TOTAL"


def test_a_combatant_with_no_build_has_no_complications():
    """Synthetic stat-block combatants, vehicles and breakables. Must not
    raise --- most of the suite is built from these."""

    class _Bare:
        id = "wall"

    assert complications_of(_Bare()) == []


# ---- and the loop must actually pass them ----

def test_the_situation_the_loop_builds_carries_them():
    from kirby_combat.loop.chooser import PhaseSituation

    actor = _with(_Raw("PSYCHOLOGICALLIMITATION", input_text="Overconfidence"))
    enemy = _with(_Raw("HUNTED", alias="Hunted"))
    enemy.id = "foe"
    situation = PhaseSituation(actor=actor, menu=[], enemies=[enemy],
                               allies=[], segment=12, turn=1)
    tactical = situation.tactical_situation()
    assert [c.name for c in tactical.actor_complications] == ["Overconfidence"]
    assert "foe" in tactical.enemy_complications
