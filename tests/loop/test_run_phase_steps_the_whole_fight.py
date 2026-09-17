"""`run_phase` is the one door that steps a fight --- the clock included.

THE DEFECT THIS PINS. `run_phase` took a session and stopped dead at the
end of a Segment: once the order was spent it returned `actor_id=None`
for ever, and only `Encounter.run_segment` / `advance_segment` could move
on. `run_encounter` knew that and held the advance itself, so a consumer
that steps a fight one Phase at a time --- which is what a networked
consumer does --- could not finish one. Its only options were to stop
after twelve Segments or to write a second copy of the advance, and a
second copy is how the post-Segment-12 Recovery, the bleeding and the
Adjustment fade come to fire in one path and not the other.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from conftest import encounter_of, fighter        # tests/loop/conftest.py

from kirby_combat.loop import FirstLegalChooser, run_encounter, run_phase
from kirby_combat.roster import Verdict
from kirby_combat.side import Side
from kirby_dice import RandomRoller

RUN_PY = pathlib.Path(__file__).resolve().parent.parent.parent / (
    "kirby_combat/loop/run.py")


def _pair(**kw):
    return encounter_of(
        fighter("a", side=Side.named("x"), dex=25, **kw),
        fighter("b", side=Side.named("y"), dex=10, **kw),
    )


# ---------------------------------------------------------------------------
# It advances
# ---------------------------------------------------------------------------

def test_it_resolves_the_order_when_the_fight_is_carrying_none():
    encounter = _pair()
    assert encounter.sessions[0].timeline.acting_order == []

    phase = run_phase(encounter, FirstLegalChooser(),
                      roller=RandomRoller(seed=3))

    assert phase.actor_id == "a"
    assert phase.session.timeline.acting_order


def test_it_does_not_resolve_a_second_order_over_one_already_standing():
    """A rehydrated fight mid-Segment carries the order its log recorded.
    Resolving another would re-roll 6E2 p.21's tie-break and draw dice the
    fight that ran never drew."""
    roller = RandomRoller(seed=3)
    encounter = _pair().run_segment(roller=lambda: roller.roll_dice(3))

    phase = run_phase(encounter, FirstLegalChooser(), roller=roller)

    assert [e.kind for e in phase.session.event_log].count(
        "ActingOrderResolved") == 1


def test_a_spent_segment_is_advanced_rather_than_refused():
    """The defect itself: the third call used to be `actor_id=None` for
    ever."""
    roller = RandomRoller(seed=3)
    encounter = _pair()

    seen = []
    for _ in range(3):
        phase = run_phase(encounter, FirstLegalChooser(), roller=roller)
        assert phase.actor_id is not None
        seen.append((phase.encounter.turn, phase.encounter.segment))
        encounter = phase.encounter

    assert seen[0] == seen[1], "both slots of one Segment"
    assert seen[2] != seen[1], "and then the clock moved"
    assert any(e.kind == "SegmentAdvanced"
               for e in phase.session.event_log)


def test_the_turn_wrap_and_its_free_recovery_fire_through_this_door():
    """6E2 p.131. The Post-Segment 12 Recovery lives in `advance_segment`,
    and the whole point of the advance living in `run_phase` is that a
    consumer stepping by Phase gets it without knowing it exists."""
    roller = RandomRoller(seed=3)
    encounter = _pair()

    for _ in range(40):
        phase = run_phase(encounter, FirstLegalChooser(), roller=roller,
                          on_unresolvable="skip")
        if phase.actor_id is None:
            break
        encounter = phase.encounter
        if any(e.kind == "RecoveryTaken" for e in phase.session.event_log):
            break

    assert any(e.kind == "RecoveryTaken" for e in phase.session.event_log)


# ---------------------------------------------------------------------------
# The one remaining `actor_id is None`
# ---------------------------------------------------------------------------

def test_a_decided_fight_returns_no_actor_and_emits_nothing():
    encounter = encounter_of(
        fighter("a", side=Side.named("x"), dex=25),
        fighter("down", side=Side.named("y"), dex=10, stun=0),
    )
    before = len(encounter.sessions[0].event_log)

    phase = run_phase(encounter, FirstLegalChooser(),
                      roller=RandomRoller(seed=3))

    assert phase.actor_id is None
    assert phase.events == []
    assert len(phase.session.event_log) == before, (
        "a decided fight must not be advanced a Segment by being asked "
        "for one more Phase"
    )


def test_a_fight_nobody_can_act_in_says_so_rather_than_spinning():
    """The honest answer when a whole Turn passes with no actor and the
    fight is still not decided. A quiet `actor_id=None` here is what would
    let a consumer loop for ever."""
    class NeverOver:
        def decide(self, roster) -> Verdict:
            return Verdict(over=False)

    # REC of zero, deliberately: 6E2 p.131's free Post-Segment 12 Recovery
    # fires inside the advance and would otherwise put one of them back on
    # his feet before the Turn was out -- which is the right rule and
    # would make this a test of the Recovery instead.
    from fixtures.synthetic_hero import synthetic_combatant
    from kirby_combat.encounter import Encounter
    from kirby_combat.session.combat_session import CombatSession
    from kirby_combat.template import CombatTemplate

    def _out(id: str, side: str, dex: int):
        return synthetic_combatant(
            id=id, name=id, spd=4, dex=dex, rec=0,
            max_stun=40, max_body=12, max_end=40,
            current_stun=0, current_body=12, current_end=40,
            side=Side.named(side),
        )

    encounter = Encounter(id="e", turn=1, segment=12, sessions=[
        CombatSession.create(
            id="s", combatants=[_out("a", "x", 25), _out("b", "y", 10)],
            scene=None, template=CombatTemplate.default_6e_superheroic(),
            dice_roller=RandomRoller(seed=7),
        ).start(),
    ])

    with pytest.raises(ValueError, match="whole"):
        run_phase(encounter, FirstLegalChooser(),
                  roller=RandomRoller(seed=3), until=NeverOver())


# ---------------------------------------------------------------------------
# And there is only one copy of it
# ---------------------------------------------------------------------------

def test_run_encounter_holds_no_advance_of_its_own():
    """DERIVED, not enumerated: this reads `run_encounter`'s own body.

    The advance is `run_segment` + `advance_segment`. `run_encounter` used
    to call both; if it ever calls either again there are two copies of
    the Segment advance, and the day one of them gains a rule the other
    does not is the day a fight run to completion and a fight stepped by
    Phase stop being the same fight.
    """
    tree = ast.parse(RUN_PY.read_text())
    body = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "run_encounter")
    called = {
        node.func.attr for node in ast.walk(body)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "run_segment" not in called
    assert "advance_segment" not in called
    assert any(
        isinstance(node, ast.Call) and getattr(node.func, "id", "") == "run_phase"
        for node in ast.walk(body)
    ), "and it does step the fight through the one door"


def test_the_two_paths_reach_the_same_fight():
    """The claim the split is for. Driven to completion, or stepped one
    Phase at a time, with the same roller: the same log."""
    driven = run_encounter(
        _pair(), FirstLegalChooser(), roller=RandomRoller(seed=21),
        on_unresolvable="skip", max_turns=8,
    )

    roller = RandomRoller(seed=21)
    encounter = _pair()
    for _ in range(8 * 12 * 12):
        phase = run_phase(encounter, FirstLegalChooser(), roller=roller,
                          on_unresolvable="skip")
        encounter = phase.encounter
        if phase.actor_id is None:
            break
    else:                                   # pragma: no cover - guard
        raise AssertionError("the stepped fight never finished")

    assert [e.kind for e in encounter.sessions[0].event_log] == \
        [e.kind for e in driven.encounter.sessions[0].event_log]
