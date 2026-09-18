"""The schema a viewer generates its types from.

THE POINT: a front end that hand-writes the event shapes holds a copy of a
contract nothing checks, and it drifts silently — which is the same defect
this package's own registry had when six of twenty-eight events could be
written and never read back. So the shapes are DERIVED from the union, the
same derivation the round-trip gate walks, and a consumer generates from
the derivation instead of retyping it.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import subprocess
import sys
import tomllib
from typing import Any, Literal

import pytest

import kirby_combat
from kirby_combat.serialization import json_schema, to_dict
from kirby_combat.serialization.schema import (
    FREE_FORM_PAYLOADS, UnmappableField,
)
from kirby_combat.session.events import EVENT_CLASSES, EVENT_KINDS, _BaseEvent


SHIPPED = pathlib.Path(kirby_combat.__file__).parent / "schema" / "events.json"
PYPROJECT = pathlib.Path(kirby_combat.__file__).parent.parent / "pyproject.toml"

#: The key stamped from `importlib.metadata`, i.e. from the INSTALLED
#: distribution. Excluded where a committed artefact is compared against a
#: freshly derived one, because that comparison would otherwise be between
#: two readings of the same environment and would agree whenever both were
#: wrong -- which is exactly how a schema tagged with a stale version was
#: committed once already. The repo-controlled check is
#: `test_the_shipped_document_names_the_version_pyproject_declares`.
VERSION_KEY = "x-kirby-combat-version"


def _shape(document: dict) -> dict:
    return {k: v for k, v in document.items() if k != VERSION_KEY}


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
    # 29, not 30, since 0.18.5: `StatusChanged` was deleted --- a second
    # event shape for a fact `StatusEffectsChanged` already carried, with
    # no producer anywhere in the engine. The floor moves with a
    # deliberate deletion; it does not move for a collapse.
    assert len(EVENT_CLASSES) >= 29


def test_the_gate_could_actually_fail():
    """The negative control, and it is planted rather than imagined.

    `_UnregisteredEvent` below is a REAL `_BaseEvent` subclass, defined
    here and deliberately absent from the `CombatEvent` union. If the
    walk were over "every event class the package defines" rather than
    over the union, it would appear in `$defs` and this would fail — so
    the test above is checking that the walk happened, not restating its
    input. (An events-module class missing from the union is a different
    property and is guarded upstream by
    `tests/serialization/test_roundtrip.py`'s walk over
    `_BaseEvent.__subclasses__()`; this file does not duplicate it.)

    `LoadedHero` keeps the other half honest: a walk over every dataclass
    in the package rather than over the events would pull it in.
    """
    schema = json_schema()

    assert _UnregisteredEvent not in EVENT_CLASSES
    assert "_UnregisteredEvent" not in schema["$defs"]
    assert "LoadedHero" not in schema["$defs"]
    # The same property, planted for the Scene tree's own carve-out
    # (`Scene.encounter`, see `FREE_FORM_PAYLOADS`): a walk that followed
    # the annotation instead of stopping at the allow-list would pull in
    # the internal fight `Encounter` carries — sessions, combatants,
    # HeroCombatant snapshots and all.
    assert "Encounter" not in schema["$defs"]
    assert "CombatSession" not in schema["$defs"]


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


def test_a_multi_value_literal_is_typed_as_well_as_enumerated():
    """`EventAuthor.type` is three strings. A bare `enum` would make a
    generator produce a weaker type than the engine guarantees — the
    value is a string either way, and the document should say so."""
    author_type = json_schema()["$defs"]["EventAuthor"]["properties"]["type"]

    assert author_type == {
        "type": "string", "enum": ["combatant", "gm", "engine"],
    }


def test_exactly_these_five_fields_are_free_form():
    """`Any` describes nothing, so it is REFUSED except on the four
    payload bags that really are free-form, PLUS `Scene.encounter` —
    which is not `Any` but is walked out of the document for the same
    reason (see the constant's docstring: walking it would grow a second,
    un-flattened copy of the session graph `SessionStateView` already
    publishes). Asserted whole, not as a subset: a field that acquires an
    `Any` annotation, or that is added to this allow-list without a
    matching reason, must fail here rather than quietly become
    unconstrained in every generated type."""
    assert FREE_FORM_PAYLOADS == {
        "ActionDeclared.parameters",
        "ActionResolved.result_payload",
        "EnvironmentalTriggered.effect",
        "GMOverride.patch",
        "Scene.encounter",
    }

    defs = json_schema()["$defs"]
    permissive = {
        f"{name}.{prop}"
        for name, definition in defs.items()
        for prop, schema in definition["properties"].items()
        if schema.get("additionalProperties") == {} or schema == {}
    }
    assert permissive == set(FREE_FORM_PAYLOADS)


def test_an_any_outside_the_allow_list_is_refused():
    """The negative control for the allow-list. Without this, the test
    above passes whether or not `Any` is actually rejected."""
    from kirby_combat.serialization.schema import _schema_for

    assert _schema_for(Any, {}, "ActionDeclared.parameters") == {}
    with pytest.raises(UnmappableField):
        _schema_for(Any, {}, "SomeEvent.some_new_field")


def test_the_id_is_a_urn_and_names_no_deployment_host():
    """A `$id` must be a URI; nothing says it must resolve. A standalone
    library naming a host would be this package claiming to know where it
    is served from."""
    document_id = json_schema()["$id"]

    assert document_id.startswith("urn:kirby-combat:schema:events:")
    assert "://" not in document_id


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
        "max_stun", "max_body", "max_end", "spd", "dex", "health", "down",
        "position", "prone", "stunned", "ko", "invisible", "perceives",
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


#: The scene's own richest fixture: at least one of everything
#: `to_dict(scene)` can emit for a populated map — a wall, a surface, a
#: hazard and a construct — so the round-trip test below exercises the
#: whole tree the viewer generates its geometry types from, not just
#: `Scene` itself.
def _a_richly_furnished_scene():
    from kirby_combat.scene.construct import Construct, ConstructEffect
    from kirby_combat.scene.scene import (
        AmbientConditions, Hazard, HazardEffect, Position, Scene,
        SceneBounds, Surface, Wall,
    )

    return Scene(
        id="sc1", name="O.K. Corral",
        bounds=SceneBounds(0, 0, 0, 50, 50, 10),
        surfaces=[
            Surface(id="floor1", name="Main floor",
                    polygon_xy=[(0, 0), (50, 0), (50, 50), (0, 50)],
                    elevation_m=0.0, surface_type="ground", cover_level=0,
                    is_supporting=True, climb_difficulty=None),
        ],
        walls=[
            Wall(id="w1", name="Corral fence",
                 segment=(Position(10, 0, 0), Position(10, 50, 0)),
                 height_m=2.0, blocks_los=True, blocks_movement=True,
                 cover_level=4, body=8, def_value=4, ed_value=4,
                 walkable_width_m=0.5, climb_difficulty=2),
        ],
        hazards=[
            Hazard(id="lava1", name="Spilled lamp oil",
                   polygon_xy=[(20, 20), (30, 20), (30, 30), (20, 30)],
                   elevation_range_m=(0.0, 0.5),
                   trigger="on_enter",
                   effect=HazardEffect(damage_dice=4, damage_type="killing",
                                        status_inflicted="on_fire")),
        ],
        ambient=AmbientConditions(light_level=2, gravity_scale=1.0,
                                   weather="fog"),
        combatant_positions={"wyatt": Position(5, 5, 0, facing=1.5)},
        constructs=[
            Construct(obj_id="fw1", kind="force_wall",
                      segment=(Position(0, 0, 0), Position(5, 0, 0)),
                      blocks_los=True, blocks_movement=True,
                      def_value=8, body=10, no_teleport_levels=2,
                      effect=ConstructEffect(kind="damage", damage_dice=2,
                                              trigger="on_enter")),
        ],
    )


def test_every_dataclass_reachable_from_scene_has_a_def():
    """The walk, not a hand-kept list: every type a populated `Scene` can
    carry gets a `$def`, the same property `test_every_registered_kind_
    has_a_schema` checks for events."""
    defs = json_schema()["$defs"]

    for name in (
        "Scene", "Wall", "Surface", "Hazard", "HazardEffect", "Furnishing",
        "Construct", "ConstructEffect", "AmbientConditions", "SceneBounds",
        "Position",
    ):
        assert name in defs, f"{name} has no $def"


def test_a_populated_scene_validates_against_its_own_schema():
    """The same property `test_a_populated_instance_validates_against_
    its_own_schema` checks for every event, over the scene's richest
    fixture: a wall, a surface, a hazard and a construct. Checked
    recursively — the nested dataclasses, not only `Scene` itself,
    because a drifted `Wall` or `Hazard` is exactly what the viewer
    hand-wrote wrong."""
    scene = _a_richly_furnished_scene()
    payload = to_dict(scene)
    defs = json_schema()["$defs"]

    def _check(value, defs):
        if isinstance(value, dict) and "__type__" in value:
            definition = defs[value["__type__"]]
            assert set(value) == set(definition["properties"])
            assert set(definition["required"]) == set(value)
            for v in value.values():
                _check(v, defs)
        elif isinstance(value, list):
            for v in value:
                _check(v, defs)
        elif isinstance(value, dict):
            for v in value.values():
                _check(v, defs)

    _check(payload, defs)
    # The property that motivated this file: a wall's segment is TWO
    # `Position` objects (`start`/`end` on the wire is wrong), not a flat
    # pair of coordinates.
    assert defs["Wall"]["properties"]["segment"] == {
        "type": "array", "items": {"$ref": "#/$defs/Position"},
    }
    # A polygon is a list of [x, y] pairs, not a flat coordinate list.
    assert defs["Surface"]["properties"]["polygon_xy"] == {
        "type": "array",
        "items": {"type": "array", "items": {"type": "number"}},
    }
    assert defs["Hazard"]["properties"]["elevation_range_m"] == {
        "type": "array", "items": {"type": "number"},
    }
    # A hazard's effect is an object, not a scalar.
    assert defs["Hazard"]["properties"]["effect"] == {
        "$ref": "#/$defs/HazardEffect",
    }
    assert defs["AmbientConditions"]["properties"]["light_level"] == {
        "type": "integer",
    }


def test_the_document_names_the_version_it_was_derived_from():
    assert json_schema()["x-kirby-combat-version"] == kirby_combat.__version__


def test_the_shipped_file_is_what_the_code_derives():
    """A committed artefact that has gone stale is worse than none: it
    passes review and generates the wrong types.

    THE SHAPE, with the version key excluded. That key is stamped from
    the installed distribution metadata, so comparing it here would be
    comparing the environment against itself: the two sides agree
    whenever they are both wrong, which is how an artefact tagged 0.17.0
    was once committed under a `pyproject.toml` that said 0.18.1 with
    this test green. The version is checked against the repo below.
    """
    assert _shape(json.loads(SHIPPED.read_text())) == _shape(json_schema())


def test_the_shipped_document_names_the_version_pyproject_declares():
    """THE GATE ON A FORGOTTEN REGENERATION, and the only version check
    that is repo-controlled rather than environment-controlled.

    `pyproject.toml`'s `[project] version` is the one statement of the
    version this repository owns; `importlib.metadata` reads whatever
    happens to be installed, which in a source checkout lags it. So the
    committed artefact is compared against the repo, and a developer
    whose editable install is stale cannot regenerate a wrongly-stamped
    schema and see green.
    """
    declared = tomllib.loads(PYPROJECT.read_text())["project"]["version"]

    assert json.loads(SHIPPED.read_text())[VERSION_KEY] == declared


def test_the_module_prints_the_shipped_file():
    out = subprocess.run(
        [sys.executable, "-m", "kirby_combat.schema"],
        capture_output=True, text=True, check=True,
    ).stdout

    assert json.loads(out) == json.loads(SHIPPED.read_text())


@dataclasses.dataclass
class _UnregisteredEvent(_BaseEvent):
    """A real event class that is NOT in the `CombatEvent` union.

    Defined here rather than in the events module on purpose: this is the
    planted control for `test_the_gate_could_actually_fail`, and the
    round-trip gate's walk over `_BaseEvent.__subclasses__()` filters to
    classes the events module defines, so this one is invisible to it.
    """

    kind: Literal["_UnregisteredEvent"] = dataclasses.field(
        default="_UnregisteredEvent", init=False)
