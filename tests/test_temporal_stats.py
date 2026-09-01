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


def test_a_drain_composes_with_a_conditional_purchase():
    """Drain Ravel's Hero-ID DEX: base 10 + 9 (Hero ID) - 4 drained = 15."""
    c = _ravel(in_hero_id=True)
    c.state.drains["dex"] = 4
    assert c.combat_stats().dex == 15


def test_the_same_drain_on_the_civilian_cannot_take_the_purchase_away():
    """Out of Hero ID the +9 was never there: 10 - 4 = 6, not 15 - 9."""
    c = _ravel(in_hero_id=False)
    c.state.drains["dex"] = 4
    assert c.combat_stats().dex == 6


def test_the_drain_rides_the_characteristic_through_an_identity_flip():
    """One drain, read in both identities: it is a contribution on DEX, so
    flipping the Hero-ID purchase in or out moves the total by the purchase
    and never re-applies or loses the drain."""
    c = _ravel(in_hero_id=True)
    c.state.drains["dex"] = 4
    assert c.combat_stats().dex == 15
    c.state.in_hero_id = False
    assert c.combat_stats().dex == 6
    c.state.in_hero_id = True
    assert c.combat_stats().dex == 15


def test_a_drain_cannot_take_a_characteristic_below_zero():
    """Civilian DEX 10 drained 12 floors at 0, not -2."""
    c = _ravel(in_hero_id=False)
    c.state.drains["dex"] = 12
    assert c.combat_stats().dex == 0


def test_an_aid_lands_on_top_of_a_floored_drain():
    """The floor is measured against the undrained value, so the 2 points of
    overshoot are spent, not banked: 10 drained 12 is 0, and an Aid of 5
    reads 5."""
    c = _ravel(in_hero_id=False)
    c.state.drains["dex"] = 12
    c.state.aids["dex"] = 5
    assert c.combat_stats().dex == 5


def test_a_drain_on_a_power_derived_defense_is_not_a_characteristic():
    """Mental Defense is bought as a Power, so a drain naming it has no
    characteristic to contribute to and is applied to the stat block."""
    c = _ravel(in_hero_id=True)
    before = c.combat_stats().md
    c.state.drains["md"] = 3
    assert c.combat_stats().md == max(0, before - 3)
