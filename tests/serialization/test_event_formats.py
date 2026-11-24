"""Every event row says which format of its kind it was written in.

Two-databases spec §6, R2 (Peter, 2026-11-24: "sep events" — a version per
event KIND, not one global number). The Danger Room replays fights
recorded today after the engine's event shapes have moved on, so each row
carries `__format__`, the format its kind had when it was written, and
`from_dict` walks a row from an older format up through that kind's
upgrade steps before building the event.

A row with no `__format__` was written before stamping existed (kirby-combat
0.39.x and earlier). Those rows ARE their kind's first format: that is a
fact about history, not a fallback, and it is the only stamp that is ever
inferred.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kirby_combat.serialization import from_dict, json_schema, to_dict
from kirby_combat.session import event_formats
from kirby_combat.session.events import (
    EVENT_CLASSES, SessionStarted, make_author_engine,
)


def _started() -> SessionStarted:
    return SessionStarted(
        id="s-evt-1", session_id="s", sequence=1,
        timestamp=datetime(2026, 11, 24, tzinfo=UTC),
        author=make_author_engine(), scene_id="", combatant_ids=["a", "b"],
    )


def test_every_row_is_stamped_with_its_kinds_format():
    row = to_dict(_started())
    assert row["__format__"] == SessionStarted.FORMAT == 1


def test_an_unstamped_row_is_its_kinds_first_format():
    row = to_dict(_started())
    del row["__format__"]
    assert from_dict(row).combatant_ids == ["a", "b"]


def test_a_row_from_a_newer_engine_is_refused():
    row = to_dict(_started())
    row["__format__"] = SessionStarted.FORMAT + 1
    with pytest.raises(event_formats.UnknownEventFormat, match="newer"):
        from_dict(row)


def test_an_older_row_is_walked_up_through_its_kinds_upgrades(monkeypatch):
    """Pretend `SessionStarted` moved to format 2, renaming a field: a
    format-1 row must arrive as a format-2 event."""
    monkeypatch.setattr(SessionStarted, "FORMAT", 2)

    def rename(row: dict) -> dict:
        row = dict(row)
        row["combatant_ids"] = row.pop("fighters")
        return row

    monkeypatch.setitem(event_formats.UPGRADES, ("SessionStarted", 1), rename)
    old = to_dict(_started())
    old["__format__"] = 1
    old["fighters"] = old.pop("combatant_ids")
    assert from_dict(old).combatant_ids == ["a", "b"]


def test_a_missing_upgrade_step_is_refused(monkeypatch):
    monkeypatch.setattr(SessionStarted, "FORMAT", 2)
    old = to_dict(_started())
    old["__format__"] = 1
    with pytest.raises(event_formats.UnknownEventFormat, match="no upgrade"):
        from_dict(old)


def test_every_kind_past_its_first_format_can_be_walked_up():
    """The guard on the registry: a kind whose FORMAT moved on must have a
    step from every earlier format, or its old rows cannot be read."""
    missing = [
        (cls.__name__, v)
        for cls in EVENT_CLASSES
        for v in range(1, cls.FORMAT)
        if (cls.__name__, v) not in event_formats.UPGRADES
    ]
    assert missing == []


def test_the_schema_pins_each_kinds_format():
    defs = json_schema()["$defs"]
    for cls in EVENT_CLASSES:
        prop = defs[cls.__name__]["properties"]["__format__"]
        assert prop == {"type": "integer", "const": cls.FORMAT}
        assert "__format__" in defs[cls.__name__]["required"]
