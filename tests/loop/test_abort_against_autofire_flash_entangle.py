"""A target may Abort against Autofire, Flash and Entangle (6E2 p.24).

`REACTABLE_KINDS` lists the kinds whose resolution reaches a roll the
Dodge's DCV is read at. Since kirby-combat #22 an Autofire burst and spray
roll at the attack door, and a one-target Flash or Entangle rolls to hit
(6E1 p.228, p.217) through `_fold_session_cvs`, where a Dodge is folded
(`test_offered_means_resolves.test_a_dodge_reaches_the_flash_roll`). So
they are attacks a man may Abort against, and until now he was never asked.

Every test drives `run_phase` with a seat that answers "dodge" when asked.
"""
from __future__ import annotations

import pytest
from shaped import Dice, armed, encounter_on, scene_with, shaped_blast  # tests/loop/shaped.py
from test_autofire_bursts import COUNTED, _gun
from test_offered_means_resolves import _effect_fight

from kirby_combat.loop import run_phase
from kirby_combat.loop.chooser import OutOfTurnReason
from kirby_combat.loop.reactions import REACTABLE_KINDS
from kirby_combat.side import Side

VILLAINS, HEROES = Side.named("villains"), Side.named("heroes")


class TakeKindDodgeWhenAsked:
    def __init__(self, kind):
        self.kind = kind
        self.asked = []

    def choose(self, situation):
        oot = situation.out_of_turn
        if oot is not None:
            self.asked.append((situation.actor.id, oot.reason, oot.attack))
            if oot.reason is OutOfTurnReason.ABORT and "dodge" in situation.action_ids:
                return "dodge"
            return situation.menu[0].action_id
        return next(a.action_id for a in situation.menu if a.kind == self.kind)


def _autofire_fight(spray):
    positions = ({"a": (0, 0, 0), "b": (6, 0, 0), "c": (8, 0, 0)} if spray
                 else {"a": (0, 0, 0), "b": (8, 0, 0)})
    people = [armed("a", _gun(), side=VILLAINS, dex=30)]
    people += [armed(t, None, side=HEROES) for t in positions if t != "a"]
    return encounter_on(scene_with(positions), *people, template=COUNTED), "b"


@pytest.mark.parametrize("kind", ["autofire", "autofire_spray", "flash", "entangle"])
def test_the_target_is_asked_and_his_abort_is_taken(kind):
    assert kind in REACTABLE_KINDS
    if kind in ("autofire", "autofire_spray"):
        enc, target = _autofire_fight(kind == "autofire_spray")
    else:
        enc, target = _effect_fight(kind.upper(), 4), "mark"
    chooser = TakeKindDodgeWhenAsked(kind)

    result = run_phase(enc, chooser, roller=Dice(face=2), on_unresolvable="raise")

    assert result.kind == kind
    asked = [(who, attack) for who, reason, attack in chooser.asked
             if reason is OutOfTurnReason.ABORT]
    assert asked and asked[0][0] == target
    assert asked[0][1].kind == kind
    aborts = [(e.combatant_id, e.to_action) for e in result.events
              if e.kind == "AbortDeclared"]
    # A spray is announced against every man in its line: each is asked.
    everyone = ["b", "c"] if kind == "autofire_spray" else [target]
    assert [who for who, _ in asked] == everyone
    assert aborts == [(who, "dodge") for who in everyone]


def test_the_dodge_reaches_the_burst():
    """+3 DCV on the burst's own roll (6E2 p.55)."""
    from shaped import payloads

    enc, _ = _autofire_fight(False)
    result = run_phase(enc, TakeKindDodgeWhenAsked("autofire"), roller=Dice(face=2),
                       on_unresolvable="raise")
    shots = [p for p in payloads(result.session) if p.get("target_id") == "b"
             and "target_dcv" in p]
    assert shots and all(p["target_dcv"] == 5 + 3 for p in shots)
