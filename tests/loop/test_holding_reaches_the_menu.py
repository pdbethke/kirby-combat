"""What you are holding has to reach the menu.

Power Lad picked the freight wagon up ELEVEN TIMES and never threw it.

`enumerate_actions` offers `throw_object` only when told `actor_holding`
and `held_construct_id`. Those are parameters, and the loop never
populated them --- exactly as `slot_allocation` was the caller's to invent
until `allocation_for` assembled it. So `pickup` resolved, the log
recorded it, and the next Phase's menu had no idea, offered the pickup
again, and he lifted the same wagon until the stalemate guard fired.

Ninth of the same shape in a week. The engine can pick a thing up and can
throw a thing; it could not remember between those two Phases that it was
holding one.

Folded from the log, absolute rather than a delta, the way `active_slots`
folds reallocations: the LATEST pickup or throw wins. A delta would be
unrecoverable the moment one was missed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from kirby_combat.holding import held_object
from kirby_combat.session.events import (
    ActionDeclared, ActionResolved, make_author_engine,
)


class _Log:
    def __init__(self, events=()):
        self.event_log = list(events)


def _base() -> dict:
    return dict(id=str(uuid.uuid4()), session_id="s1", sequence=1,
                timestamp=datetime.now(timezone.utc),
                author=make_author_engine())


def _did(who: str, kind: str, payload: dict) -> list:
    declared = ActionDeclared(**_base(), combatant_id=who, action_type=kind,
                              targets=[])
    resolved = ActionResolved(**_base(), declaration_event_id=declared.id,
                              result_payload={"kind": kind, **payload})
    return [declared, resolved]


def test_nothing_held_at_the_start():
    assert held_object(_Log(), "lad") is None


def test_a_pickup_leaves_him_holding_it():
    log = _Log(_did("lad", "pickup", {"object_id": "freight-wagon"}))
    assert held_object(log, "lad") == "freight-wagon"


def test_throwing_it_empties_his_hands():
    log = _Log(_did("lad", "pickup", {"object_id": "freight-wagon"})
               + _did("lad", "throw_object", {"object_id": "freight-wagon"}))
    assert held_object(log, "lad") is None


def test_the_latest_pickup_wins():
    """Absolute, not a delta --- the same discipline `active_slots` holds
    to, and for the same reason."""
    log = _Log(_did("lad", "pickup", {"object_id": "barrel"})
               + _did("lad", "pickup", {"object_id": "freight-wagon"}))
    assert held_object(log, "lad") == "freight-wagon"


def test_somebody_elses_hands_are_not_his():
    log = _Log(_did("ike", "pickup", {"object_id": "barrel"}))
    assert held_object(log, "lad") is None
