"""A Stunned man spends his next Phase recovering, and only that one.

6E2 p.106: "A character who's Stunned or recovering from being Stunned can
take no Actions". p.107: "In the character's next full Phase after becoming
Stunned, he recovers ... recovering from being Stunned is all he can do that
Phase."

`stunned_or_recovering_for` folded that window for a long time, and it
gated the CV penalty, the Abort and the move --- but not the Phase. A
Stunned man chose an action every time his Phase came round: in prod fight
33bf8bee a Stunned fighter chose a close-and-strike twice, the move was
refused because he cannot move, and the menu offered it again.
"""
from __future__ import annotations

from dataclasses import replace

from conftest import encounter_of, fighter          # tests/loop/conftest.py
from kirby_combat.loop import run_phase
from kirby_combat.session.apply import apply_event
from kirby_combat.session.events import ActionResolved, make_author_engine
from kirby_combat.side import Side
from kirby_dice import RandomRoller


class _Dodges:
    def choose(self, situation):
        return next(a for a in situation.menu if a.kind == "dodge").action_id


def _stun(encounter, who: str):
    s = encounter.sessions[0]
    s = apply_event(s, ActionResolved(
        id=f"stun-{len(s.event_log)}", session_id=s.id, sequence=len(s.event_log) + 1,
        timestamp=s.event_log[-1].timestamp, author=make_author_engine(),
        declaration_event_id="",
        result_payload={"kind": "attack", "target_id": who, "status_changes": ["Stunned"]},
    ))
    return replace(encounter, sessions=[s])


def _phase(encounter):
    return run_phase(encounter, _Dodges(), roller=RandomRoller(seed=8))


def _spent(result):
    return [(e.combatant_id, e.reason) for e in result.events if e.kind == "PhaseSpent"]


def _fight():
    # Both SPD 4: Phases in Segments 3, 6, 9 and 12. Fast goes first in each.
    return encounter_of(fighter("fast", side=Side.named("x"), dex=30),
                        fighter("slow", side=Side.named("y"), dex=10))


def test_stunned_after_his_phase_he_loses_the_next_one_and_only_that():
    enc = _fight()
    r = _phase(enc)                              # Segment 12: fast
    r = _phase(r.encounter)                      # Segment 12: slow acts
    assert _spent(r) == [("slow", "acted")]
    enc = _stun(r.encounter, "slow")             # ... and is Stunned after
    r = _phase(enc)                              # Segment 3: fast
    r = _phase(r.encounter)                      # Segment 3: slow recovers
    assert r.actor_id == "slow" and _spent(r) == [("slow", "stunned")]
    r = _phase(r.encounter)                      # Segment 6: fast
    r = _phase(r.encounter)                      # Segment 6: slow acts again
    assert r.actor_id == "slow" and _spent(r) == [("slow", "acted")]


def test_stunned_before_his_dex_in_the_same_segment_that_phase_is_his_recovery():
    """Stunned in Segment 12 before his DEX comes up, his Phase in Segment
    12 IS "the character's next full Phase after becoming Stunned". He
    loses that one; Segment 3 is his again. No `SegmentAdvanced` marks a
    recovery inside the Segment of the hit, so without the loop recording
    the forfeit the fold would wait for Segment 3 and cost him two."""
    enc = _fight()
    r = _phase(enc)                              # Segment 12: fast
    enc = _stun(r.encounter, "slow")             # fast's blow Stuns slow
    r = _phase(enc)                              # Segment 12: slow recovers
    assert r.actor_id == "slow" and _spent(r) == [("slow", "stunned")]
    r = _phase(r.encounter)                      # Segment 3: fast
    r = _phase(r.encounter)                      # Segment 3: slow
    assert r.actor_id == "slow" and _spent(r) == [("slow", "acted")]
