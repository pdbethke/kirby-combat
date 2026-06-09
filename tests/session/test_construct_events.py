"""Construct events follow the frozen _BaseEvent pattern (spec §1.2, §1.7)."""
from datetime import datetime, timezone
from kirby_combat.session.events import (
    ConstructDamaged, ConstructSpawned, make_author_engine,
)


def _ts():
    return datetime(2026, 6, 9, tzinfo=timezone.utc)


def test_construct_damaged_event_shape():
    e = ConstructDamaged(id="e1", session_id="s", sequence=5, timestamp=_ts(),
                         author=make_author_engine(), construct_id="w3",
                         body_through=4, body_after=4, destroyed=False,
                         by_combatant="gorgon")
    assert e.kind == "ConstructDamaged" and e.construct_id == "w3"
    assert e.destroyed is False and e.by_combatant == "gorgon"


def test_construct_spawned_event_shape():
    e = ConstructSpawned(id="e2", session_id="s", sequence=6, timestamp=_ts(),
                         author=make_author_engine(), construct_id="fw1",
                         construct_kind="force_wall", def_value=5, body=4,
                         source_combatant="cheshire")
    assert e.kind == "ConstructSpawned" and e.construct_kind == "force_wall"
    assert e.def_value == 5 and e.source_combatant == "cheshire"
