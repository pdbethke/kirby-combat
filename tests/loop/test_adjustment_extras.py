"""Follow-up K2b: the Adjustment pieces #13 left unbuilt.

Several Drains on one stat fade separately (6E1 p.139), Delayed Return Rate
(6E1 p.142), and Healing a Drained characteristic (6E1 p.234). Each goes
through `resolve_chosen` with offers from `enumerate_actions`, and the fade
through the Encounter's own Post-Segment 12, and fails on origin/main.
"""
from __future__ import annotations

from types import SimpleNamespace

from conftest import fighter                             # tests/loop/conftest.py
from test_adjustment_powers_bite import (                # tests/loop/
    HEROES, HIT, VILLAINS, _Power, _drainer, _healer, _offer, _session, _use, _with,
)

from kirby_combat.encounter import Encounter


def _wrap(session, turns: int = 1):
    """Run the clock through ``turns`` Post-Segment 12s."""
    enc = Encounter(id="e", turn=1, segment=12, sessions=[session])
    for _ in range(turns):
        enc = enc.advance_segment()                 # 12 -> 1: the fade
        for _ in range(11):
            enc = enc.advance_segment()
    return enc.sessions[0]


def test_two_drains_on_one_stat_return_separately():
    """6E1 p.139: "The character recovers 5 points per Turn from each Drain
    separately". Two Drains DEX of 15 points each take DEX 20 to 5; after a
    Turn each has given back 5 (20 still drained, DEX 10). Lumped together
    they would have given back 5 between them (25 drained, DEX 8)."""
    session = _session(_drainer("DEX"), fighter("chiron", side=HEROES, dex=20))
    once = _use(session, "leech", "drain", "chiron", [HIT, [5, 5, 5]]).session
    twice = _use(once, "leech", "drain", "chiron", [HIT, [5, 5, 5]]).session
    assert twice.combatants["chiron"].combat_stats().dex == 5
    after = _wrap(twice)
    assert after.combatants["chiron"].combat_stats().dex == 10
    faded = [e for e in after.event_log if e.kind == "AdjustmentFaded"]
    assert sorted(e.remaining_delta for e in faded) == [-10, -10]
    assert len({e.adjustment_id for e in faded}) == 2


def _slow_drainer(option: str):
    power = _Power("DRAIN", 3, "DEX", ranged=True)
    power.assigned_modifiers = [SimpleNamespace(xmlid="DELAYEDRETURNRATE", option_id=option)]
    return _with(fighter("leech", side=VILLAINS), power)


def test_a_delayed_return_rate_drain_comes_back_on_its_own_clock():
    """6E1 p.142, "5 Points per Minute": a Minute is 5 Turns (6E2 p.18's
    12-second Turn), so nothing returns for four Turns and 5 points at the
    fifth."""
    session = _session(_slow_drainer("MINUTE"), fighter("chiron", side=HEROES, dex=20))
    drained = _use(session, "leech", "drain", "chiron", [HIT, [5, 5, 5]])
    assert drained.result["fade_interval_turns"] == 5
    four = _wrap(drained.session, turns=4)
    assert four.combatants["chiron"].combat_stats().dex == 13
    five = _wrap(drained.session, turns=5)
    assert five.combatants["chiron"].combat_stats().dex == 15


def test_healing_heals_a_drained_characteristic_and_it_stays_healed():
    """6E1 p.234: "Healing can Heal back BODY or other Characteristics lost
    in any manner, such as ... Drains", and "The points gained from Healing
    do not fade". A Drain BODY of 18 takes 9 BODY (half effect, p.143) off
    max and current alike; Healing BODY 4d6 of sixes is 24, halved to 12,
    and the 9 come back --- and nothing returns again at the Post-Segment 12."""
    patient = fighter("patient", side=HEROES)
    session = _session(_drainer("BODY"), _healer(), patient)
    drained = _use(session, "leech", "drain", "patient", [HIT, [6, 6, 6]]).session
    hurt = drained.combatants["patient"]
    assert hurt.combat_stats().max_body == 12 - 9 and hurt.state.current_body == 3
    healed = _use(drained, "doc", "heal", "patient", [[6, 6, 6, 6]])
    assert healed.result["drain_healed"] == {"BODY": 9}
    well = healed.session.combatants["patient"]
    assert well.combat_stats().max_body == 12 and well.state.current_body == 12
    later = _wrap(healed.session).combatants["patient"]
    assert later.combat_stats().max_body == 12 and later.state.current_body == 12


def test_healing_is_offered_on_a_man_whose_only_loss_is_a_drain():
    session = _session(_drainer("BODY"), _healer(), fighter("patient", side=HEROES))
    drained = _use(session, "leech", "drain", "patient", [HIT, [6, 6, 6]]).session
    assert _offer(drained, "doc", "heal", "patient")
