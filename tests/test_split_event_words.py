"""The split's words reach the combat log (`SlotsAllocated.effect_text`).

Kerendor's Magical Powers (6E1 p.406) as `test_split_offer` builds it; the
opening is driven through `run_phase`, so the event is the resolver's own.
Needs the licensed template (skips without KIRBY_COST_HDT).
"""
from __future__ import annotations

from dataclasses import replace

from kirby_combat.encounter import Encounter
from kirby_combat.loop import run_phase
from kirby_combat.side import Side
from kirby_combat.session.combat_session import CombatSession
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller

from tests.test_split_offer import _kerendor, fighter


class _Answers:
    def __init__(self, tail):
        self.tail = tail

    def choose(self, situation):
        assert situation.opening
        (offer,) = situation.menu
        return offer.action_id + "=" + self.tail


def _opening(tail):
    hero = _kerendor()
    hero = replace(hero, state=replace(hero.state, slot_points={}))
    session = CombatSession.create(
        id="s", combatants=[hero, fighter("foe", side=Side.named("villains"))],
        scene=None, template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=7)).start()
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    phase = run_phase(enc, _Answers(tail), roller=RandomRoller(seed=7))
    (alloc,) = [e for e in phase.events if e.kind == "SlotsAllocated"]
    return phase, alloc


def test_an_opening_split_is_told_in_words():
    _phase, alloc = _opening("bolt@40+wind@20")
    assert alloc.effect_text == "Blast 8d6, Flight 20m"


def test_an_opening_with_everything_off_says_so():
    _phase, alloc = _opening("")
    assert alloc.effect_text == "nothing switched on"


def test_no_split_reaches_the_log_without_words():
    phase, _ = _opening("bolt@60")
    allocs = [e for e in phase.session.event_log if e.kind == "SlotsAllocated"]
    assert allocs and all(e.effect_text for e in allocs)
