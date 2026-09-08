"""Where the suite's real characters come from.

kirby-combat READS NO .hdc FILES, here or anywhere (2026-09-08). A character
reaches this engine as a costed `LoadedHero` and never as a path: HDC's only
role is one-time import, and re-parsing it at test time meant the shape the
product actually rests on — a canonical costed build — was never exercised by
the suite that guards it.

So the suite reads BUILD DOCS: `kirby_cost.io.build_json`'s canonical
document, written once by whoever imported the .hdc, read back with
`build_from_json`. No prose, round-trippable, and the same shape a file
corpus wants.

kirby-combat commits no character data either way. The docs this suite used
to have as .hdc were the maintainer's own — Ravel, Bokor and PowerLad — and
they live in a directory named by an environment variable, SKIPPED when it is
not set. A directory rather than three variables, and no default: a path into
a maintainer's home is not shippable, and a variable that names one reads as
configured while behaving as absent everywhere else.

To produce them, once, from outside this package:

    python -c "import json,sys;from kirby_cost.io.hdc_loader import HDCLoader; \
      from kirby_cost.io.build_json import to_build_json; \
      json.dump(to_build_json(HDCLoader().load_file(sys.argv[1])), \
                open(sys.argv[2],'w'))" Ravel.hdc Ravel.json

Tests that assert MECHANICS rather than ingestion should not come here at
all. A synthetic stub states its input as data, runs everywhere, and does not
depend on anyone's build staying the shape the test assumed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import pytest

#: The variable naming a directory of BUILD DOCS (`<Name>.json`). Renamed
#: from KIRBY_COMBAT_AUTHORED deliberately: the contents changed format, and
#: a stale value silently pointing at .hdc files should read as unset rather
#: than as broken.
AUTHORED_ENV = "KIRBY_COMBAT_BUILDS"

#: The characters cleared for use as corpus, and what each one is here for.
AUTHORED = {
    "Ravel": "frameworks (multipower + VPP), martial maneuvers, duplicate xmlids",
    "Bokor": "an AVAD attack, framework and non-framework attacks side by side",
    "PowerLad": "movement powers, fractional costs",
}


def authored_root() -> Optional[Path]:
    """The directory holding the authored characters, or None if unset."""
    raw = os.environ.get(AUTHORED_ENV, "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser()
    return root if root.is_dir() else None


def authored_doc(name: str) -> Optional[Path]:
    """``<authored root>/<name>.json``, if the root is set and it exists."""
    root = authored_root()
    if root is None:
        return None
    candidate = root / f"{name}.json"
    return candidate if candidate.exists() else None


def require_authored_doc(name: str) -> dict:
    """The raw build DOC, for the few tests that must rebuild it themselves.

    `require_authored` hands back a hero that was costed once. A test that
    changes the rules costing happens under -- `CampaignRules`, say -- has to
    build it again INSIDE that context, and needs the document to do it.
    """
    path = authored_doc(name)
    if path is None:
        pytest.skip(
            f"{name}.json not available — set {AUTHORED_ENV} to a directory "
            f"holding build docs for {', '.join(sorted(AUTHORED))}."
        )
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def require_authored(name: str) -> Any:
    """An authored character as a LOADED BUILD, or skip the test.

    Returns what `HeroCombatant.from_build` takes, which is the whole point
    of this helper: no test should hold a path, because holding a path is
    how re-parsing creeps back in.

    Skips rather than fails: the build is the maintainer's own and is not in
    the repository, so its absence is a configuration state, not a defect.
    """
    from kirby_cost.io.build_json import build_from_json

    path = authored_doc(name)
    if path is None:
        pytest.skip(
            f"{name}.json not available — set {AUTHORED_ENV} to a directory "
            f"holding build docs for {', '.join(sorted(AUTHORED))}. "
            f"See this module's docstring for how to write them."
        )
    with open(path, encoding="utf-8") as fh:
        return build_from_json(json.load(fh))
