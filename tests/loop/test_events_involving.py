"""Which rows of the record concern one fighter.

"Who knocked Talisman out" meant reading every row of a 400-row fight and
knowing which keys of which kinds name a man. That is the engine's
knowledge of its own events, so the engine answers it: `events_involving`.
"""
from __future__ import annotations

from shaped import Dice, Picks, armed, encounter_on, scene_with, shaped_blast

from kirby_combat import events_involving
from kirby_combat.loop import run_phase
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


def _fight():
    enc = encounter_on(
        scene_with({"shooter": (0, 0, 0), "mark": (5, 0, 0), "bystander": (40, 0, 0)}),
        armed("shooter", shaped_blast("blast", 8), side=VILLAINS, dex=30),
        armed("mark", None, side=HEROES),
        armed("bystander", None, side=HEROES, dex=5))
    result = run_phase(enc, Picks(lambda a, _s: a.kind == "attack" and a.target_id == "mark"),
                       roller=Dice(face=2), on_unresolvable="raise")
    return result.encounter.sessions[0]


def test_the_shot_and_its_damage_concern_the_man_it_hit():
    kinds = [e.kind for e in events_involving(_fight(), "mark")]
    assert "ActionDeclared" in kinds and "ActionResolved" in kinds and "VitalsChanged" in kinds


def test_they_concern_the_man_who_fired_it():
    rows = events_involving(_fight(), "shooter")
    assert any(e.kind == "VitalsChanged" and e.combatant_id == "mark" for e in rows)


def test_a_man_nobody_touched_is_not_in_them():
    """The acting order names everyone; it is not something that happened to him."""
    rows = events_involving(_fight(), "bystander")
    assert not [e for e in rows if e.kind in ("ActionDeclared", "ActionResolved", "VitalsChanged")]
    assert not [e for e in rows if e.kind == "ActingOrderResolved"]


def test_it_is_the_record_in_order():
    session = _fight()
    rows = events_involving(session, "mark")
    assert [e.sequence for e in rows] == sorted(e.sequence for e in rows)


def test_a_list_of_dicts_is_read_dict_by_dict():
    """`SquadOrdersGiven.teams` names its men inside a list of dicts; so may
    an action's result. Both are read, at the top of a row and inside it."""
    from types import SimpleNamespace

    from kirby_combat.session.involvement import involves

    orders = SimpleNamespace(teams=[{"member_ids": ["a"]}, {"member_ids": ["b", "c"]}])
    assert involves(orders, "c") and not involves(orders, "d")
    resolved = SimpleNamespace(result_payload={"hits": [{"target_id": "x"}]})
    assert involves(resolved, "x") and not involves(resolved, "y")
