"""A Large body is easier to hit, as its sheet says (`kirby_combat.size`).

The Bestiary's Riding Horse: "Large (4m; +2 OCV for others to hit ...)"."""
from __future__ import annotations

import pytest

from tests.conftest_grips import _CHARS, gun
from kirby_combat.actions.recording import _fold_session_cvs
from kirby_combat.hero_view import HeroCombatant
from kirby_combat.models import AttackInput, DiceValues
from kirby_combat.session import CombatSession
from kirby_combat.size import ocv_to_hit
from kirby_combat.template import RAW_HEROIC
from kirby_dice import FakeRoller


@pytest.fixture(autouse=True)
def _template_needed():
    from tests.corpus import require_template
    require_template()


def _body(id_, *complications, guns=()):
    from kirby_cost.io.build_json import build_from_json

    hero = build_from_json({
        "name": id_, "template": "builtIn.Heroic6E.hdt", "base_points": 100,
        "disad_points": 0, "experience": 0, "characteristics": _CHARS,
        "powers": list(guns), "skills": [], "perks": [], "talents": [],
        "martial_arts": [], "equipment": [],
        "disadvantages": [{"id": f"d{i}", "xmlid": "PHYSICALLIMITATION", "base_cost": 0.0,
                           "alias": "Physical Complication", "input": text}
                          for i, text in enumerate(complications)]})
    return HeroCombatant.from_build(hero, id=id_)


LARGE = "Large (4m; +2 OCV for others to hit, +2 to PER Rolls for others to perceive)"


def test_the_number_is_read_off_the_sheet():
    assert ocv_to_hit(_body("horse", LARGE)) == 2
    assert ocv_to_hit(_body("man")) == 0


def test_every_shot_at_him_gets_it():
    shooter = _body("shooter", guns=[gun("g", "Gun")])
    horse, man = _body("horse", LARGE), _body("man")
    session = CombatSession.create(id="s", combatants=[shooter, horse, man], scene=None,
                                   template=RAW_HEROIC, dice_roller=FakeRoller([])).start()

    def ocv_at(target_id):
        attack = AttackInput(attacker=session.combatants["shooter"],
                             target=session.combatants[target_id],
                             power=session.combatants["shooter"].attacks[0],
                             distance_m=2, aim=None, dice=DiceValues())
        return _fold_session_cvs(session, attack).ocv_modifier

    assert ocv_at("horse") - ocv_at("man") == 2
