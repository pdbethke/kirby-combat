"""Reallocating a Multipower is a Zero Phase Action, once a Phase.

6E1 p.410: "A character can change the way his Multipower reserve points
are distributed or allocated as a Zero Phase Action. However, unless the GM
permits otherwise, he may not distribute or allocate reserve points more
than once in a Phase."

The loop spent the whole Phase on it, so a man who switched slots never
fired the slot he switched to --- and a first-offer seat (kirby-api's
benchmark fight, 2026-10-26) had Bullet reallocate every Phase from Turn 4
to the cap, so the fight never ended.
"""
from __future__ import annotations

from conftest import encounter_of, fighter      # tests/loop/conftest.py
from kirby_combat.encounter import Encounter
from kirby_combat.loop import run_phase
from kirby_combat.side import Side
from kirby_dice import RandomRoller


def _framework():
    from kirby_combat.models import FrameworkView, SlotView

    return FrameworkView(
        framework_id="fw1", xmlid="MULTIPOWER", name="Tricks",
        kind="multipower", reserve_or_pool=45,
        slots=[SlotView(slot_id=f"s{i}", name=f"s{i}", active_points=40,
                        variable=False, kind="attack") for i in (1, 2)],
    )


class Reallocates:
    """Reallocates whenever it may; otherwise the first offer."""

    def __init__(self):
        self.menus = []

    def choose(self, situation):
        if getattr(situation, "out_of_turn", None) is not None:
            return situation.menu[0].action_id
        self.menus.append([a.kind for a in situation.menu])
        for a in situation.menu:
            if a.kind == "reallocate":
                return a.action_id
        return situation.menu[0].action_id


def _fight():
    lad = fighter("lad", side=Side.named("heroes"), dex=30)
    lad.framework_view = lambda: [_framework()]       # type: ignore[method-assign]
    foe = fighter("foe", side=Side.named("villains"), dex=10)
    return encounter_of(lad, foe)


def test_a_reallocation_leaves_the_phase_his():
    chooser = Reallocates()
    first = run_phase(_fight(), chooser, roller=RandomRoller(seed=1),
                      on_unresolvable="raise")

    assert first.kind == "reallocate"
    assert not [e for e in first.events if e.kind == "PhaseSpent"]
    assert first.actor_id == "lad"


def test_the_same_phase_comes_back_without_the_offer_and_he_acts():
    chooser = Reallocates()
    first = run_phase(_fight(), chooser, roller=RandomRoller(seed=1),
                      on_unresolvable="raise")
    again = Encounter(id="e", turn=first.session.timeline.turn,
                      segment=first.session.timeline.segment,
                      sessions=[first.session])
    second = run_phase(again, chooser, roller=RandomRoller(seed=2),
                       on_unresolvable="raise")

    assert second.actor_id == "lad"
    assert "reallocate" in chooser.menus[0]
    assert "reallocate" not in chooser.menus[1]
    assert second.kind != "reallocate"
    assert [e for e in second.events if e.kind == "PhaseSpent"
            and e.combatant_id == "lad"]
