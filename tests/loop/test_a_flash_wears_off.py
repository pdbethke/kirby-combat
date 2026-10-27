"""A Flash blinds for its Segments, narrows the menu, and then ends.

6E1 p.228: "The total number of BODY rolled, minus the target's Flash Defense
(if any), is the number of Segments the target's Sense(s) is (are) disabled.
Begin counting the Segments in the Segment in which the character uses the
Flash attack". And: "If a character's affected by a Flash, generally he
can't suffer any further effect from other Flashes of the same Sense Group
... until the first Flash wears off."

THE TWO DEFECTS. Nothing called `Flash.recover`, so a Flashed man stayed
Flashed for the rest of the fight. And `run_phase` never passed
`observer_flashed_groups` to `enumerate_actions`, so a man blinded in the
Sight Group was still offered every shot that needs sight.
"""
from __future__ import annotations

from dataclasses import replace

from conftest import encounter_of, fighter          # tests/loop/conftest.py
from kirby_combat.actions.flash import Flash
from kirby_combat.loop import run_phase
from kirby_combat.side import Side
from kirby_dice import RandomRoller


class _Records:
    """Dodges every Phase, and keeps the menu ``watch`` was offered."""

    def __init__(self, watch: str):
        self.watch = watch
        self.menus: list[tuple[int, list]] = []

    def choose(self, situation):
        if getattr(situation, "out_of_turn", None) is not None:
            return situation.menu[0].action_id
        if situation.actor.id == self.watch:
            self.menus.append((situation.segment, list(situation.menu)))
        return next(a for a in situation.menu if a.kind == "dodge").action_id


def _flash(encounter, who: str, segments: int):
    s, _ = Flash.apply(encounter.sessions[0], attacker_id="fast", target_id=who,
                       sense_group="sight", body_dealt=segments, flash_defense=0)
    return replace(encounter, sessions=[s])


def _fight():
    # Both SPD 4: Phases in Segments 3, 6, 9 and 12. Fast acts first.
    return encounter_of(fighter("fast", side=Side.named("x"), dex=30),
                        fighter("slow", side=Side.named("y"), dex=10))


def _attacks(menu) -> list[str]:
    return [a.action_id for a in menu if a.kind == "attack"]


def _run(encounter, chooser, phases: int):
    roller = RandomRoller(seed=8)
    for _ in range(phases):
        encounter = run_phase(encounter, chooser, roller=roller,
                              on_unresolvable="raise").encounter
    return encounter


def test_a_flashed_man_is_not_offered_the_shot_he_cannot_see_to_make():
    chooser = _Records("slow")
    enc = _run(_fight(), chooser, 1)           # Segment 12: fast
    enc = _flash(enc, "slow", 3)               # fast Flashes slow, Segment 12
    _run(enc, chooser, 1)                      # Segment 12: slow
    segment, menu = chooser.menus[-1]
    assert segment == 12
    assert _attacks(menu) == [], "a Sight-Flashed man aimed his Blast"


def test_the_flash_counts_down_a_segment_at_a_time_and_ends():
    """3 Segments used in Segment 12: blind in 12, 1 and 2; gone by 3."""
    chooser = _Records("slow")
    enc = _run(_fight(), chooser, 1)
    enc = _flash(enc, "slow", 3)
    enc = _run(enc, chooser, 3)                # slow@12, fast@3, slow@3
    s = enc.sessions[0]
    remaining = [e.segments_remaining for e in s.event_log
                 if e.kind == "FlashRecovered" and e.target_id == "slow"]
    assert remaining == [2, 1, 0]
    assert Flash.is_flashed(s, "slow") == (False, {})
    segment, menu = chooser.menus[-1]
    assert segment == 3
    assert _attacks(menu), "the Flash wore off and he still could not shoot"


def test_a_second_flash_on_a_flashed_group_has_no_further_effect():
    enc = _flash(_fight(), "slow", 4)
    enc = _flash(enc, "slow", 9)
    assert Flash.is_flashed(enc.sessions[0], "slow")[1] == {"sight": 4}
