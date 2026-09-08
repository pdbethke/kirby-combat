"""Knowing it isn't working --- the doctrine the lot never had.

Seven armed men emptied revolvers into Power Lad for twenty-eight Phases.
Every shot that LANDED got nothing through his 25 rPD, and not one of them
ever tried anything else. Nothing in twenty-two tactics says "that is not
working".

It is not a morale gap, though it looks like one. HERO has no morale stat
for an individual: PRE is the stat, and 6E2 p.140's worked example makes
that explicit --- Howler's "demoralized henchmen are about to run" and she
fixes it with a Presence Attack. But terror scales with the terrifier's
PRE, and Power Lad's is 10, so nothing he does will ever break them. What
breaks them is arithmetic they can do themselves.

THE FACT, NOT A MOOD. A miss proves nothing --- you might hit next time.
A blow that LANDED and did no BODY proves something specific: the thing
you are shooting cannot be hurt by what you are shooting it with. Counted
per target, from the session's own log, because it is exactly what the
man swinging would know.

Complements `withdraw_when_outmatched`, which was narrowed this same day
to fighters carrying nothing at all. This is the case that narrowing gave
up: armed, and it makes no difference.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from conftest import fighter                      # tests/loop/conftest.py
from kirby_combat.futility import futile_hits
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_engine,
)
from kirby_combat.side import Side
from kirby_combat.tactics.base import Situation
from kirby_combat.tactics.library import all_tactics


def _base() -> dict:
    return dict(id=str(uuid.uuid4()), session_id="s1", sequence=1,
                timestamp=datetime.now(timezone.utc),
                author=make_author_engine())


def _shot(who: str, at: str, *, hit: bool, body: int) -> list:
    declared = ActionDeclared(**_base(), combatant_id=who,
                              action_type="attack", targets=[at])
    resolved = ActionResolved(**_base(), declaration_event_id=declared.id,
                              result_payload={"hit": hit, "body_dealt": body,
                                              "stun_dealt": 0, "target_id": at})
    return [declared, resolved]


class _Log:
    def __init__(self, events):
        self.event_log = events


def test_a_landed_blow_that_did_nothing_counts():
    log = _Log(_shot("wyatt", "power_lad", hit=True, body=0))
    assert futile_hits(log, "wyatt") == {"power_lad": 1}


def test_a_miss_proves_nothing_and_is_not_counted():
    """You might hit next time. Only a LANDED blow is evidence."""
    log = _Log(_shot("wyatt", "power_lad", hit=False, body=0))
    assert futile_hits(log, "wyatt") == {}


def test_a_blow_that_drew_blood_is_not_futile():
    log = _Log(_shot("wyatt", "billy", hit=True, body=4))
    assert futile_hits(log, "wyatt") == {}


def test_only_your_own_blows_count():
    """What the man swinging knows, not what the room knows."""
    log = _Log(_shot("doc", "power_lad", hit=True, body=0))
    assert futile_hits(log, "wyatt") == {}


def test_they_add_up_per_target():
    events = (_shot("wyatt", "power_lad", hit=True, body=0)
              + _shot("wyatt", "power_lad", hit=True, body=0)
              + _shot("wyatt", "billy", hit=True, body=3))
    assert futile_hits(_Log(events), "wyatt") == {"power_lad": 2}


# ---- The doctrine ----

def _tactic():
    return next(t for t in all_tactics() if t.name == "break_off_when_nothing_works")


def _situation(events):
    actor = fighter("wyatt", side=Side.named("law"), armed=True)
    monster = fighter("power_lad", side=Side.solo("power_lad"), armed=True)
    return Situation(actor=actor, allies=[], enemies=[monster],
                     current_segment=12, turn=1, session=_Log(events))


def test_it_does_not_fire_before_the_evidence_is_in():
    """One shot that bounced is bad luck; a doctrine that runs on it would
    have men fleeing every fight."""
    assert not _tactic().applicable(_situation(
        _shot("wyatt", "power_lad", hit=True, body=0)))


def test_it_fires_once_the_man_has_proved_it_to_himself():
    events = []
    for _ in range(3):
        events += _shot("wyatt", "power_lad", hit=True, body=0)
    tactic = _tactic()
    situation = _situation(events)
    assert tactic.applicable(situation)
    assert tactic.execute(situation).steps[0].kind == "disengage"


def test_it_does_not_fire_while_something_is_still_working():
    """Hitting one man uselessly is no reason to leave a fight you are
    winning against somebody else."""
    events = []
    for _ in range(3):
        events += _shot("wyatt", "power_lad", hit=True, body=0)
    situation = _situation(events)
    situation.enemies.append(fighter("billy", side=Side.named("cow"), armed=True))
    events += _shot("wyatt", "billy", hit=True, body=5)
    assert not _tactic().applicable(situation)


# ---- A side learns together ----

def test_a_side_pools_what_it_watched():
    """PeterB: "the cowboys and the earps qualify as teams".

    A man landing one blow for nothing has bad luck; three men landing
    one each have a fact between them, and they were standing close
    enough to watch. Measured at the Corral: nineteen shots at Power Lad,
    FIVE of them landing, and no individual ever reached three -- OCV 5
    against DCV 6 means they mostly miss. The evidence was in the fight
    the whole time and no single man held enough of it.

    This is not the metagaming perception forbids. Watching your mate's
    bullet strike a man and do nothing is an observation.
    """
    events = (_shot("wyatt", "power_lad", hit=True, body=0)
              + _shot("doc", "power_lad", hit=True, body=0)
              + _shot("morgan", "power_lad", hit=True, body=0))
    actor = fighter("wyatt", side=Side.named("law"), armed=True)
    allies = [fighter("doc", side=Side.named("law"), armed=True),
              fighter("morgan", side=Side.named("law"), armed=True)]
    situation = Situation(
        actor=actor, allies=allies,
        enemies=[fighter("power_lad", side=Side.solo("power_lad"), armed=True)],
        current_segment=12, turn=1, session=_Log(events))
    assert _tactic().applicable(situation), (
        "three men watched three bullets bounce; that is a fact between them"
    )


def test_an_enemys_failure_teaches_you_nothing():
    """Guards the guard. The pool is your SIDE, not the room -- a Cowboy
    watching an Earp fail is watching a man he is trying to kill."""
    events = (_shot("frank", "power_lad", hit=True, body=0)
              + _shot("tom", "power_lad", hit=True, body=0)
              + _shot("billy", "power_lad", hit=True, body=0))
    actor = fighter("wyatt", side=Side.named("law"), armed=True)
    situation = Situation(
        actor=actor, allies=[],
        enemies=[fighter("power_lad", side=Side.solo("power_lad"), armed=True)],
        current_segment=12, turn=1, session=_Log(events))
    assert not _tactic().applicable(situation)


def test_one_man_still_needs_three_of_his_own():
    """A lone fighter has only his own evidence, and the bar does not drop
    because he is alone."""
    events = _shot("wyatt", "power_lad", hit=True, body=0) * 1
    actor = fighter("wyatt", side=Side.named("law"), armed=True)
    situation = Situation(
        actor=actor, allies=[],
        enemies=[fighter("power_lad", side=Side.solo("power_lad"), armed=True)],
        current_segment=12, turn=1, session=_Log(events))
    assert not _tactic().applicable(situation)
