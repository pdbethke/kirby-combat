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

To produce them, once, from the cleared .hdc (with KIRBY_COST_HDT set):

    python scripts/write_build_docs.py <dir holding Ravel.hdc etc> <out dir>
    KIRBY_COMBAT_BUILDS=<out dir> pytest

NOT FROM THE .json BESIDE THE .hdc. `kirby-cost/tests/fixtures/authored/`
holds oracle dumps next to the authored files; they look like build docs and
are not (no costing header, `complications` for `disadvantages`), and loaded
as one they lose every framework (Warp review 2026-10-20, F2). A doc without
the canonical header is refused by name below.

UNSET SKIPS; SET-BUT-WRONG FAILS. A directory that is missing, incomplete or
holds the wrong shape is a configured run that would otherwise go green on
fewer characters than it claims, or red with what reads as an engine defect.

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


#: The top-level keys `kirby_cost.io.build_json.to_build_json` always writes
#: and an oracle dump never has. The header is what costing reads; a doc
#: without it is some other document.
CANONICAL_KEYS = ("template", "base_points", "disad_points", "experience", "disadvantages")

_WRITE_THEM = "Write them with scripts/write_build_docs.py (see tests/corpus.py)."


def authored_root() -> Optional[Path]:
    """The directory holding the authored characters; None only if UNSET.

    Set to something that is not a directory is a failure, not a skip.
    """
    raw = os.environ.get(AUTHORED_ENV, "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser()
    if not root.is_dir():
        pytest.fail(f"{AUTHORED_ENV}={raw!r} is not a directory. {_WRITE_THEM}")
    return root


def authored_doc(name: str) -> Optional[Path]:
    """``<authored root>/<name>.json``; None only if the variable is unset.

    A configured corpus missing a cleared character fails by name.
    """
    root = authored_root()
    if root is None:
        return None
    candidate = root / f"{name}.json"
    if not candidate.exists():
        pytest.fail(
            f"{AUTHORED_ENV} is set but {candidate} does not exist; it must hold "
            f"{', '.join(f'{n}.json' for n in sorted(AUTHORED))}. {_WRITE_THEM}"
        )
    return candidate


def _read_build_doc(path: Path) -> dict:
    """The doc at ``path``, refused unless it is a canonical build doc."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    missing = [k for k in CANONICAL_KEYS if not isinstance(doc, dict) or k not in doc]
    if missing:
        pytest.fail(
            f"{path} is not a canonical build doc: it lacks {', '.join(missing)}. "
            f"An oracle dump (the .json beside each .hdc in kirby-cost's "
            f"fixtures) looks like one and loses every framework. {_WRITE_THEM}"
        )
    return doc


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
    return _read_build_doc(path)


def require_authored(name: str) -> Any:
    """An authored character as a LOADED BUILD, or skip the test.

    Returns what `HeroCombatant.from_build` takes, which is the whole point
    of this helper: no test should hold a path, because holding a path is
    how re-parsing creeps back in.

    Skips when the corpus is UNSET: the build is the maintainer's own and is
    not in the repository, so its absence is a configuration state. A corpus
    that is set fails instead when the doc is missing or the wrong shape.
    """
    from kirby_cost.io.build_json import build_from_json

    path = authored_doc(name)
    if path is None:
        pytest.skip(
            f"{name}.json not available — set {AUTHORED_ENV} to a directory "
            f"holding build docs for {', '.join(sorted(AUTHORED))}. "
            f"See this module's docstring for how to write them."
        )
    return build_from_json(_read_build_doc(path))


#: kirby-cost needs a HERO Designer template to cost anything, and ships
#: none -- so does the CI runner, deliberately. `require_authored` covers
#: the tests that also want a character; this covers the ones that build a
#: doc inline and still need the engine to price it.
TEMPLATE_ENV = "KIRBY_COST_HDT"


def require_template() -> None:
    """Skip unless a .hdt is configured AND usable.

    Checked by CONSTRUCTING the provider rather than by reading the
    variable: a path that is set but wrong fails deep inside costing with
    a message about templates, which reads like an engine defect. Ask the
    question where the answer is cheap.
    """
    from kirby_cost.template.hdt_provider import HDTTemplateProvider

    try:
        HDTTemplateProvider()
    except Exception as exc:                            # noqa: BLE001
        pytest.skip(f"no usable {TEMPLATE_ENV}: {exc}")
