"""A complication's severity reaches the page from a REAL build.

6E1 Complications grade a Psychological Complication on two rungs: how
often it comes up (Uncommon / Common / Very Common) and how hard it holds
(Moderate / Strong / Total). "Vengeful (Total)" and "Not Brave (Moderate)"
are different instructions, and the Brief was written to say which.

It never did, for any character loaded through kirby-cost.
`complications_of` read the adders off ``raw.adders`` and, failing that,
parsed ``raw.adder_string``. kirby-cost has neither: it keeps them on
``assigned_adders``, which is where `rage.py` has always read them. The
two tests that covered severity built stubs with an ``adder_string`` the
real loader does not produce, so they passed and the page dropped every
severity in the O.K. Corral (2026-11-27): Wyatt Earp's Vengeful (Very
Common, Total) printed exactly like Billy Claiborne's Not Brave.

This builds the complication the way an import does --- a build doc
through `build_from_json` --- and asks the engine.
"""
from __future__ import annotations

import pytest

from tests.corpus import require_template
from kirby_cost.io.build_json import build_from_json
from kirby_combat.brief import Brief
from kirby_combat.complications import complications_of
from kirby_combat.enumeration import LegalAction
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.loop.chooser import PhaseSituation


def _psych(text: str, situation: str, intensity: str) -> dict:
    return {
        "id": f"d-{text}", "xmlid": "PSYCHOLOGICALLIMITATION", "base_cost": 0.0,
        "min_cost": 0.0, "alias": "Psychological Complication", "input": text,
        "adders": [
            {"xmlid": "SITUATION", "option_id": situation, "base_cost": 10.0,
             "selected": True, "required": True, "include_in_base": True},
            {"xmlid": "INTENSITY", "option_id": intensity, "base_cost": 5.0,
             "selected": True, "required": True, "include_in_base": True},
        ],
    }


def _man(*complications: dict) -> HeroCombatant:
    require_template()
    doc = {
        "name": "Marshal", "template": "builtIn.Heroic6E.hdt",
        "base_points": 175, "disad_points": 50, "experience": 0,
        "characteristics": [], "powers": [], "skills": [], "perks": [],
        "talents": [], "martial_arts": [], "equipment": [],
        "disadvantages": list(complications),
    }
    return HeroCombatant.from_build(build_from_json(doc), id="marshal")


def test_the_intensity_is_read_off_the_build():
    got = complications_of(_man(_psych("Never leaves a partner", "VERYCOMMON", "TOTAL")))
    assert got[0].adders.get("INTENSITY") == "TOTAL"
    assert got[0].adders.get("SITUATION") == "VERYCOMMON"


def test_the_page_says_how_hard_it_holds():
    man = _man(_psych("Never leaves a partner", "VERYCOMMON", "TOTAL"),
               _psych("Afraid of horses", "COMMON", "MODERATE"))
    menu = [LegalAction(action_id="dodge", kind="dodge", target_id=None,
                        power_xmlid=None, power_name=None, summary="Dodge")]
    page = Brief(PhaseSituation(actor=man, menu=menu, segment=12, turn=1)).render()
    assert "Never leaves a partner (Total)" in page, page
    assert "Afraid of horses (Moderate)" in page, page
