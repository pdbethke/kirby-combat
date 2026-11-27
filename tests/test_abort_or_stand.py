"""The Abort question has doctrine, and a man's complications answer it.

See `tactics/catalog/abort_or_stand.py`. 6E2 p.23-24: an Abort costs his
next Phase. A model seat at the Corral aborted every shot and two Cowboys
the record has fighting to the end never fired (2026-11-27).
"""
from __future__ import annotations

import pytest

from tests.corpus import require_template
from kirby_combat.brief import Brief
from kirby_combat.enumeration import LegalAction
from kirby_combat.loop.chooser import OutOfTurn, OutOfTurnReason, PhaseSituation, TacticChooser


@pytest.fixture(autouse=True)
def _template_needed():
    require_template()


def _psych(text):
    return {"id": f"d-{text}", "xmlid": "PSYCHOLOGICALLIMITATION", "base_cost": 0.0,
            "min_cost": 0.0, "alias": "Psychological Complication", "input": text,
            "adders": [{"xmlid": "SITUATION", "option_id": "COMMON", "base_cost": 10.0,
                        "selected": True, "required": True, "include_in_base": True},
                       {"xmlid": "INTENSITY", "option_id": "STRONG", "base_cost": 5.0,
                        "selected": True, "required": True, "include_in_base": True}]}


def _man(*complications, armed=True):
    from kirby_cost.io.build_json import build_from_json
    from kirby_combat.hero_view import HeroCombatant

    gun = {"id": "g", "xmlid": "RKA", "name": "Revolver", "levels": 2, "input": "PD",
           "modifiers": [{"xmlid": "FOCUS", "option_id": "OAF", "base_cost": -1.0}]}
    hero = build_from_json({
        "name": "m", "template": "builtIn.Heroic6E.hdt", "base_points": 175,
        "disad_points": 50, "experience": 0, "characteristics": [],
        "powers": [gun] if armed else [], "skills": [], "perks": [], "talents": [],
        "martial_arts": [], "equipment": [], "disadvantages": list(complications)})
    return HeroCombatant.from_build(hero, id="m")


def _abort(actor):
    menu = [LegalAction(action_id="no_abort", kind="no_abort", target_id=None,
                        power_xmlid=None, power_name=None, summary="Don't Abort"),
            LegalAction(action_id="dodge", kind="dodge", target_id=None,
                        power_xmlid=None, power_name=None, summary="Abort to Dodge")]
    return PhaseSituation(actor=actor, menu=menu, segment=3, turn=1,
                          out_of_turn=OutOfTurn(reason=OutOfTurnReason.ABORT,
                                                by_id="x", incoming=None, attack=None))


@pytest.mark.parametrize("comps,armed,expected", [
    ((), True, "no_abort"),                              # whole and armed
    ((), False, "dodge"),                                # nothing to shoot with
    ((_psych("Not Brave"),), True, "dodge"),             # Billy Claiborne
    ((_psych("Vengeful"),), True, "no_abort"),           # Wyatt Earp
    ((_psych("No fear of death"),), False, "no_abort"),  # Doc, even empty-handed
])
def test_doctrine_answers_the_abort(comps, armed, expected):
    assert TacticChooser().choose(_abort(_man(*comps, armed=armed))) == expected


def test_the_abort_page_carries_the_advice():
    page = Brief(_abort(_man(_psych("Vengeful")))).render()
    assert "abort_or_stand -> no_abort" in page, page
    assert "costs your NEXT Phase" in page


def test_the_page_says_why_for_him():
    """The tactic's reason for THIS man, not only its general advice: an
    unarmed man is told he has nothing to shoot back with."""
    page = Brief(_abort(_man(armed=False))).render()
    assert "For you: he has nothing to shoot back with" in page, page
    coward = Brief(_abort(_man(_psych("Not Brave")))).render()
    assert "For you: Not Brave: he ducks" in coward, coward
