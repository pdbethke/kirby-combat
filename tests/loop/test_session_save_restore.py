"""A fight saved mid-way restores, and carries on as if it never stopped.

THE DEFECT THIS PINS. `to_dict` wrote a whole `CombatSession` and
`from_dict` could not read it back: it raised `unknown type
'CombatTemplate'` on the first nested object it had never been told about.
The existing round-trip test only ever round-tripped events one at a time,
so a consumer that saved the SESSION --- which is what "save the fight"
means --- found out on the first load.

So this saves a fight that has really been fought, through JSON text (the
wire, not a Python dict that happens to share objects), restores it, and
asks two things: is it the same fight, and does it keep going the same way.
"""
from __future__ import annotations

import json
from dataclasses import replace

from conftest import fighter  # tests/loop/conftest.py

from kirby_combat.encounter import Encounter
from kirby_combat.loop import FirstLegalChooser, run_phase
from kirby_combat.serialization.from_dict import from_dict
from kirby_combat.serialization.to_dict import to_dict
from kirby_combat.session import CombatSession
from kirby_combat.side import Side
from kirby_combat.template import CombatTemplate
from kirby_dice import RandomRoller


#: Saved early enough that nobody is down yet, so the fight has somewhere
#: left to go after the restore.
PHASES_BEFORE_SAVE = 2


def _fight() -> Encounter:
    session = CombatSession.create(
        id="s",
        combatants=[
            fighter("a", side=Side.named("blue"), dex=20),
            fighter("b", side=Side.named("red"), dex=15),
            fighter("c", side=Side.named("red"), dex=11),
        ],
        scene=None,
        template=CombatTemplate.default_6e_superheroic(),
        dice_roller=RandomRoller(seed=7),
    ).start()
    return Encounter(id="e", turn=1, segment=12, sessions=[session])


def _step(encounter: Encounter, phases: int, seed: int) -> Encounter:
    roller = RandomRoller(seed=seed)
    for _ in range(phases):
        phase = run_phase(
            encounter, FirstLegalChooser(), roller=roller,
            on_unresolvable="skip",
        )
        encounter = phase.encounter
    return encounter


def _save_and_restore(session: CombatSession) -> CombatSession:
    return from_dict(json.loads(json.dumps(to_dict(session))))


def _vitals(session: CombatSession) -> dict:
    return {
        cid: (c.current_stun, c.current_body, c.current_end)
        for cid, c in session.combatants.items()
    }


def test_a_saved_session_restores_as_the_same_fight():
    session = _step(_fight(), phases=PHASES_BEFORE_SAVE, seed=3).sessions[0]

    restored = _save_and_restore(session)

    assert isinstance(restored, CombatSession)
    assert to_dict(restored) == to_dict(session)
    # OBJECTS, not their wire form: comparing `to_dict` output alone is how
    # timestamps came back as str unnoticed --- a str and the datetime it
    # was written from serialise to the same text.
    assert restored.template == session.template
    assert restored.timeline == session.timeline
    assert restored.event_log == session.event_log
    assert restored.statuses == session.statuses
    assert restored.created_at == session.created_at
    assert restored.status == session.status
    assert _vitals(restored) == _vitals(session)


def test_a_restored_session_fights_on_exactly_like_the_original():
    encounter = _step(_fight(), phases=PHASES_BEFORE_SAVE, seed=3)
    session = encounter.sessions[0]

    restored = _save_and_restore(session)
    # The dice are not part of the fight's record: whoever resumes a fight
    # hands it a roller, exactly as whoever starts one does. Both sides get
    # the same fresh one so any divergence is the restore's, not the dice's.
    session = replace(session, dice_roller=RandomRoller(seed=13))
    restored = replace(restored, dice_roller=RandomRoller(seed=13))
    resumed = Encounter(
        id="e", turn=restored.timeline.turn,
        segment=restored.timeline.segment, sessions=[restored],
    )
    original = Encounter(
        id="e", turn=session.timeline.turn,
        segment=session.timeline.segment, sessions=[session],
    )

    went_on = _step(original, phases=6, seed=11).sessions[0]
    resumed_on = _step(resumed, phases=6, seed=11).sessions[0]

    assert len(resumed_on.event_log) > len(restored.event_log)
    assert [e.kind for e in resumed_on.event_log] == [
        e.kind for e in went_on.event_log]
    assert _vitals(resumed_on) == _vitals(went_on)
    assert resumed_on.timeline.aborts == went_on.timeline.aborts
