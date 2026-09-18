"""The shipped schema artefact.

`events.json` beside this file is what `serialization.json_schema()`
derives, written out at release time and carried in the wheel, so a
consumer pins an engine version and reads the schema out of the package
it pinned. `python -m kirby_combat.schema` prints it.

NEVER EDIT IT BY HAND. Regenerate it, from the repository root:

    .venv/bin/python -c "
    import json
    from kirby_combat.serialization import json_schema
    open('kirby_combat/schema/events.json','w').write(
        json.dumps(json_schema(), indent=2, sort_keys=True) + '\\n')
    "

`tests/serialization/test_json_schema.py` fails if the file and the
derivation disagree, because a committed artefact that has gone stale is
worse than none: it passes review and generates the wrong types.
"""
import pathlib

SCHEMA_PATH = pathlib.Path(__file__).parent / "events.json"

__all__ = ["SCHEMA_PATH"]
