"""Ravel fights as the Hero, not as the civilian."""
import json

from kirby_cost.io.build_json import build_from_json
from kirby_combat.hero_view import HeroCombatant, HeroCombatState

RAVEL = "/home/pdbethke/PycharmProjects/Kirby/kirby-cost/tests/fixtures/authored/Ravel.json"


def _ravel(in_hero_id: bool = True) -> HeroCombatant:
    hero = build_from_json(json.load(open(RAVEL)))
    st = HeroCombatState(current_stun=1, current_body=1, current_end=1,
                         in_hero_id=in_hero_id)
    return HeroCombatant(id="ravel", hero=hero, state=st)


def test_in_hero_id_he_fights_with_the_stats_he_bought():
    s = _ravel(in_hero_id=True).combat_stats()
    assert s.dex == 19
    assert s.spd == 5


def test_as_a_civilian_he_fights_with_his_base():
    s = _ravel(in_hero_id=False).combat_stats()
    assert s.dex == 10
    assert s.spd == 2


def test_the_flip_is_visible_on_the_next_read():
    c = _ravel(in_hero_id=True)
    assert c.combat_stats().dex == 19
    c.state.in_hero_id = False
    assert c.combat_stats().dex == 10
