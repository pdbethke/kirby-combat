"""The schema a viewer generates its types from.

THE POINT: a front end that hand-writes the event shapes holds a copy of a
contract nothing checks, and it drifts silently — which is the same defect
this package's own registry had when six of twenty-eight events could be
written and never read back. So the shapes are DERIVED from the union, the
same derivation the round-trip gate walks, and a consumer generates from
the derivation instead of retyping it.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

import kirby_combat
from kirby_combat.serialization import json_schema, to_dict
from kirby_combat.session.events import EVENT_CLASSES, EVENT_KINDS


SHIPPED = pathlib.Path(kirby_combat.__file__).parent / "schema" / "events.json"


def _an_instance(cls):
    """One of these, built from the base fields alone — every concrete
    event gives all of its own fields a default, so this is a total
    constructor over the union. The same trick the round-trip gate uses,
    and for the same reason: no per-class table to go stale."""
    from datetime import datetime, timezone

    from kirby_combat.session.events import make_author_engine

    return cls(
        id="evt-x", session_id="s1", sequence=1,
        timestamp=datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc),
        author=make_author_engine(),
    )


def test_every_registered_kind_has_a_schema():
    """THE PROPERTY, over the union rather than a list somebody kept."""
    schema = json_schema()

    defs = schema["$defs"]
    missing = sorted(c.__name__ for c in EVENT_CLASSES if c.__name__ not in defs)
    assert missing == [], f"registered kinds with no schema: {missing}"
    assert len(EVENT_CLASSES) >= 30


def test_the_gate_could_actually_fail():
    """The negative control, FIRST. A dataclass that is not in the union
    must be absent from the document — otherwise the test above passes
    whether or not the walk happened."""
    schema = json_schema()

    assert "_NotAnEvent" not in schema["$defs"]
    assert "LoadedHero" not in schema["$defs"]


def test_the_oneof_is_the_union_and_discriminates_on_kind():
    schema = json_schema()

    refs = {entry["$ref"].rsplit("/", 1)[-1] for entry in schema["oneOf"]}
    assert refs == {c.__name__ for c in EVENT_CLASSES}
    for kind, cls in EVENT_KINDS.items():
        assert schema["$defs"][cls.__name__]["properties"]["kind"]["const"] == kind


def test_the_wire_tag_is_on_every_event_schema():
    """`to_dict` writes `__type__` on every dataclass it emits, so a
    consumer's type must carry it or its parse of a real row fails."""
    schema = json_schema()

    for cls in EVENT_CLASSES:
        props = schema["$defs"][cls.__name__]["properties"]
        assert props["__type__"]["const"] == cls.__name__


@pytest.mark.parametrize("cls", EVENT_CLASSES, ids=lambda c: c.__name__)
def test_a_populated_instance_validates_against_its_own_schema(cls):
    """Every key `to_dict` writes is a key the schema declares, and every
    key the schema requires is one `to_dict` writes. Checked by set
    equality rather than a validator library — this package takes no
    third-party schema dependency."""
    payload = to_dict(_an_instance(cls))
    definition = json_schema()["$defs"][cls.__name__]

    assert set(payload) == set(definition["properties"])
    assert set(definition["required"]) == set(payload)


def test_the_timestamp_is_typed_as_the_string_it_goes_out_as():
    """`to_dict` writes an ISO string for a `datetime` field. Typing it
    `date-time` string is what the wire is; typing it anything else would
    be the schema describing Python rather than JSON."""
    ts = json_schema()["$defs"]["SessionStarted"]["properties"]["timestamp"]

    assert ts == {"type": "string", "format": "date-time"}


def test_the_session_state_shape_is_published_beside_the_events():
    """The shape `rewind_to_sequence` exposes, so a viewer's fold can be
    checked against the engine's."""
    defs = json_schema()["$defs"]

    assert set(defs["SessionStateView"]["properties"]) == {
        "__type__", "status", "turn", "segment", "last_sequence",
        "next_actor_id", "combatants",
    }
    assert set(defs["CombatantStateView"]["properties"]) == {
        "__type__", "id", "name", "side",
        "current_stun", "current_body", "current_end",
        "max_stun", "max_body", "max_end", "health", "down",
        "position", "prone", "stunned", "ko", "hidden", "perceives",
    }
    # `position` is nullable (a combatant not on the map), and the
    # generator must emit that as `PositionView | null` rather than
    # silently dropping the null branch — a viewer that assumed a
    # position would put an absent man at the origin.
    assert defs["CombatantStateView"]["properties"]["position"] == {
        "anyOf": [{"$ref": "#/$defs/PositionView"}, {"type": "null"}],
    }
    assert set(defs["PositionView"]["properties"]) == {
        "__type__", "x", "y", "z", "facing",
    }


def test_the_document_names_the_version_it_was_derived_from():
    assert json_schema()["x-kirby-combat-version"] == kirby_combat.__version__


def test_the_shipped_file_is_what_the_code_derives():
    """A committed artefact that has gone stale is worse than none: it
    passes review and generates the wrong types."""
    assert json.loads(SHIPPED.read_text()) == json_schema()


def test_the_module_prints_the_shipped_file():
    out = subprocess.run(
        [sys.executable, "-m", "kirby_combat.schema"],
        capture_output=True, text=True, check=True,
    ).stdout

    assert json.loads(out) == json_schema()
