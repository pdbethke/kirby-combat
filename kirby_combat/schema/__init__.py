"""The shipped schema artefact.

`events.json` beside this file is what `serialization.json_schema()`
derives, written out at release time and carried in the wheel, so a
consumer pins an engine version and reads the schema out of the package
it pinned. `python -m kirby_combat.schema` prints it.

NEVER EDIT IT BY HAND. Regenerate it, from the repository root, WITH THE
INSTALLED METADATA UP TO DATE:

    .venv/bin/python -c "
    import json
    from kirby_combat.serialization import json_schema
    open('kirby_combat/schema/events.json','w').write(
        json.dumps(json_schema(), indent=2, sort_keys=True) + '\\n')
    "

`x-kirby-combat-version` is stamped from `importlib.metadata`, i.e. from
the INSTALLED distribution -- which in a source checkout can lag
`pyproject.toml`'s `[project] version` and has produced a wrongly-stamped
artefact once already. So regenerating from a stale editable install
writes a schema carrying the wrong version, and
`test_the_shipped_document_names_the_version_pyproject_declares` is the
gate that catches it: it parses `pyproject.toml` and refuses any other
answer. If it fails after a regeneration, the install is stale, not the
schema -- reinstall (`pip install -e .`) and regenerate again.

`tests/serialization/test_json_schema.py` also fails if the file and the
derivation disagree in SHAPE, because a committed artefact that has gone
stale is worse than none: it passes review and generates the wrong
types.
"""
import pathlib

SCHEMA_PATH = pathlib.Path(__file__).parent / "events.json"

__all__ = ["SCHEMA_PATH"]
