"""JSON Schema for the event log — DERIVED, never written out.

A consumer that renders this engine's fights generates its types from
this document, so its event shapes are the engine's by construction. The
alternative is what was measured in the viewer: a hand-written copy of a
snapshot, drifting silently against a surface that had already been
replaced.

ONE DERIVATION, THE SAME ONE. The walk starts at `EVENT_CLASSES`, which is
`get_args(CombatEvent)` — the union itself, and the same list the type
registry and the round-trip gate read. There is no second list of events
here to forget to update.

IT DESCRIBES THE WIRE, NOT PYTHON. `to_dict` writes `__type__` on every
dataclass, an ISO string for a `datetime`, a list for a tuple and a sorted
list for a set, so those are what the schemas say. A schema that described
the Python types would be a correct document about the wrong thing.

NO THIRD-PARTY SCHEMA LIBRARY. This package declares three dependencies
and none of them is a schema generator; `dataclasses` and `typing` answer
every question the walk asks.
"""
from __future__ import annotations

import dataclasses
import datetime
import types
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from kirby_combat.session.events import EVENT_CLASSES, EventAuthor
# RUNTIME import, deliberately. `events.py` imports `ActionIntent` under
# `if TYPE_CHECKING:`, so `get_type_hints(ActingOrderResolved)` raises
# `NameError` without it in the namespace. Importing it here rather than
# relaxing the guard there keeps that module's import graph as it is.
from kirby_combat.session.timeline import ActionIntent
from kirby_combat.session.state_view import (
    CombatantStateView, PositionView, SessionStateView,
)
from kirby_combat.scene.scene import (
    AmbientConditions, Furnishing, Hazard, HazardEffect, Position, Scene,
    SceneBounds, Surface, Wall,
)
from kirby_combat.scene.construct import Construct, ConstructEffect
# RESOLUTION ONLY. `scene.py` imports `Encounter` under `if TYPE_CHECKING:`,
# so `get_type_hints(Scene)` raises `NameError` without it in the namespace
# — same reason `ActionIntent` is imported above. `Encounter` is never
# walked: see `FREE_FORM_PAYLOADS`'s `Scene.encounter` entry.
from kirby_combat.encounter import Encounter

_LOCALNS: dict[str, Any] = {
    "ActionIntent": ActionIntent,
    "EventAuthor": EventAuthor,
    "CombatantStateView": CombatantStateView,
    "PositionView": PositionView,
    "Scene": Scene,
    "SceneBounds": SceneBounds,
    "Position": Position,
    "AmbientConditions": AmbientConditions,
    "Surface": Surface,
    "Wall": Wall,
    "Hazard": Hazard,
    "HazardEffect": HazardEffect,
    "Furnishing": Furnishing,
    "Construct": Construct,
    "ConstructEffect": ConstructEffect,
    "Encounter": Encounter,
}

#: THE ONLY FIELDS ALLOWED TO BE FREE-FORM, named one at a time.
#:
#: Four of these are `Any`: it has no JSON Schema meaning, and mapping it
#: to `{}` — "anything at all" — is a permissive default of exactly the
#: kind this module refuses everywhere else. They are the payload bags the
#: engine writes whatever a particular action produced into, and no closed
#: shape describes them.
#:
#: The fifth, `Scene.encounter`, is not `Any` — it types as `Encounter |
#: None` — but is free-form for the same reason: `Encounter.sessions` is
#: `list["CombatSession"]`, the full internal fight (combatants, HeroCombatant
#: snapshots and all) that `SessionStateView` above exists to publish
#: separately, as its own flat, read-only projection — see that module's
#: docstring: "a viewer that needs those reads the record". Walking `Scene`
#: into `Encounter` would grow a second, un-flattened copy of that same
#: graph inside this one document, which is the drift `SessionStateView`
#: was built to stop. A `Scene` on the wire is walls, surfaces, hazards
#: and constructs; every fixture in this package's own test suite leaves
#: `encounter` at its `None` default.
#:
#: Every OTHER `Any` is a mistake, and raises. Listed as `Class.field` and
#: asserted whole by `tests/serialization/test_json_schema.py`, so a field
#: that acquires an `Any` annotation — or a field that needs this same
#: carve-out — fails the build rather than quietly becoming unconstrained
#: in every consumer's generated types.
FREE_FORM_PAYLOADS: frozenset[str] = frozenset({
    "ActionDeclared.parameters",
    "ActionResolved.result_payload",
    "EnvironmentalTriggered.effect",
    "GMOverride.patch",
    "Scene.encounter",
})

#: 2020-12 is what a schema-to-types generator reads and what `$defs`
#: belongs to; draft-07's `definitions` would be a second spelling.
_DIALECT = "https://json-schema.org/draft/2020-12/schema"


class UnmappableField(TypeError):
    """A field whose type has no JSON Schema meaning.

    RAISED, never skipped. A field quietly left out of the document is a
    field a consumer's generated type does not have, and the consumer
    finds out by reading `undefined` off a real row.
    """


def _schema_for(annotation: Any, defs: dict[str, dict], where: str) -> dict:
    """`where` is the `Class.field` this annotation was reached through —
    carried the whole way down so the `Any` refusal can name the field a
    reader has to go and fix, and so the free-form allow-list is checked
    against a field rather than against a type."""
    origin = get_origin(annotation)

    if annotation is Any:
        if where in FREE_FORM_PAYLOADS:
            return {}
        raise UnmappableField(
            f"{where} is annotated `Any`, which describes nothing. Give it "
            f"a serialisable type, or — if it really is a free-form payload "
            f"bag — add it to FREE_FORM_PAYLOADS deliberately."
        )
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is str:
        return {"type": "string"}
    if annotation is datetime.datetime:
        # `to_dict` writes `.isoformat()`. See the module docstring.
        return {"type": "string", "format": "date-time"}
    if origin is Literal:
        values = list(get_args(annotation))
        # The type goes on BOTH branches. A multi-value `Literal` of
        # strings is still a string on the wire, and emitting a bare
        # `enum` makes a generator produce a weaker type than the engine
        # actually guarantees.
        typed = (
            {"type": "string"} if values and all(isinstance(v, str) for v in values)
            else {}
        )
        if len(values) == 1:
            return {**typed, "enum": values, "const": values[0]}
        return {**typed, "enum": values}
    if origin in (types.UnionType, Union):
        parts = [a for a in get_args(annotation) if a is not type(None)]
        nullable = len(parts) != len(get_args(annotation))
        inner = (
            _schema_for(parts[0], defs, where) if len(parts) == 1
            else {"anyOf": [_schema_for(p, defs, where) for p in parts]}
        )
        return {"anyOf": [inner, {"type": "null"}]} if nullable else inner
    if origin in (list, tuple, set, frozenset):
        # A tuple and a set both go out as a list (JSON has neither), and
        # a set goes out sorted. The item type is the first argument;
        # `tuple[int, ...]`'s Ellipsis is not one.
        args = [a for a in get_args(annotation) if a is not Ellipsis]
        return {
            "type": "array",
            "items": _schema_for(args[0], defs, where) if args else {},
        }
    if origin is dict:
        _key, value = get_args(annotation)
        return {
            "type": "object",
            "additionalProperties": _schema_for(value, defs, where),
        }
    if dataclasses.is_dataclass(annotation):
        return {"$ref": f"#/$defs/{_define(annotation, defs)}"}

    raise UnmappableField(
        f"no JSON Schema meaning for {annotation!r}; give the field a "
        f"serialisable type or a mapping here"
    )


def _define(cls: type, defs: dict[str, dict]) -> str:
    """Add `cls` to `defs` (idempotent, cycle-safe) and return its name."""
    name = cls.__name__
    if name in defs:
        return name
    defs[name] = {}  # placeholder first, so a self-reference terminates

    hints = get_type_hints(cls, localns=_LOCALNS)
    properties: dict[str, dict] = {
        # `to_dict` tags every dataclass. A consumer's parser
        # discriminates on `kind` for events and on this for everything
        # else, so it is part of the shape, not decoration.
        "__type__": {"type": "string", "const": name, "enum": [name]},
    }
    required = ["__type__"]
    for field in dataclasses.fields(cls):
        where = f"{name}.{field.name}"
        # SHORT-CIRCUITED, not walked. `where in FREE_FORM_PAYLOADS` is
        # checked here — before `hints[field.name]` is handed to
        # `_schema_for` — so a field named for this exact reason (see
        # `Scene.encounter`'s entry) never resolves its own annotation
        # into a `$ref` at all, and never recurses into a graph this
        # document does not otherwise reach.
        properties[field.name] = (
            {} if where in FREE_FORM_PAYLOADS
            else _schema_for(hints[field.name], defs, where)
        )
        required.append(field.name)

    defs[name] = {
        "type": "object",
        "title": name,
        "properties": properties,
        "required": required,
        # CLOSED. `to_dict` writes exactly the declared fields plus
        # `__type__`, so anything else on a row is a row this engine did
        # not write, and a viewer should say so rather than render it.
        "additionalProperties": False,
    }
    return name


def json_schema() -> dict:
    """Every event kind, the session-state shape, and the version.

    The document is a discriminated union: `oneOf` over one `$def` per
    event class, each pinning `kind` to a `const`. A schema-to-types
    generator turns that into a union a `switch (event.kind)` narrows
    exhaustively, which is the property the consumer needs — an unhandled
    kind is then a compile error rather than a dropped frame.
    """
    import kirby_combat

    defs: dict[str, dict] = {}
    events = sorted(EVENT_CLASSES, key=lambda c: c.__name__)
    for cls in events:
        _define(cls, defs)
    _define(SessionStateView, defs)
    # THE SCENE'S SHAPE, published the same way: `Scene` and everything it
    # reaches (`Wall`, `Surface`, `Hazard`, `HazardEffect`, `Furnishing`,
    # `Construct`, `ConstructEffect`, `AmbientConditions`, `SceneBounds`,
    # `Position`) walked as authored in `scene/`, not retyped here. A
    # consumer that hand-writes its own geometry types drifts against this
    # engine's own wire shape exactly as a hand-written event shape would —
    # measured, in a viewer, as a `Wall.segment` read as `Wall.start`/`end`,
    # a polygon read as flat coordinates rather than pairs, and a hazard's
    # `effect` read as a scalar rather than the object it is.
    _define(Scene, defs)

    return {
        "$schema": _DIALECT,
        # A URN, not a URL. A `$id` must be a URI and nothing says it
        # must resolve — and a standalone library naming a deployment
        # host would be this package claiming to know where it is served
        # from, which it does not and which nothing answers at.
        "$id": f"urn:kirby-combat:schema:events:{kirby_combat.__version__}",
        "title": "CombatEvent",
        "x-kirby-combat-version": kirby_combat.__version__,
        "oneOf": [{"$ref": f"#/$defs/{cls.__name__}"} for cls in events],
        "$defs": defs,
    }


__all__ = ["FREE_FORM_PAYLOADS", "UnmappableField", "json_schema"]
