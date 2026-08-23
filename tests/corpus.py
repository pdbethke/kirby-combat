"""Where the suite's real character files come from.

kirby-combat commits no `.hdc` files. A character file is a machine-readable
build, and the ones this suite used to carry were published Hero Games
characters from the Champions Villains packs — committing those redistributes
stat blocks, however useful they are as test data. kirby-cost settled the same
question the same way; see its `tests/corpus.py` and `.gitignore`.

So real-file tests read the maintainer's own authored characters — Ravel,
Bokor and PowerLad — from a directory named by an environment variable, and
SKIP when it is not set. A directory rather than three variables, and no
default: a path into a maintainer's home is not shippable, and a variable
that names one reads as configured while behaving as absent everywhere else.

Tests that assert MECHANICS rather than ingestion should not come here at
all. A synthetic stub states its input as data, runs everywhere, and does not
depend on anyone's build staying the shape the test assumed.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pytest

#: The variable naming a directory that holds the authored `.hdc` files.
AUTHORED_ENV = "KIRBY_COMBAT_AUTHORED"

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


def authored_hdc(name: str) -> Optional[Path]:
    """``<authored root>/<name>.hdc``, if the root is set and the file exists."""
    root = authored_root()
    if root is None:
        return None
    candidate = root / f"{name}.hdc"
    return candidate if candidate.exists() else None


def require_authored(name: str) -> str:
    """The path to an authored character, or skip the test.

    Skips rather than fails: the file is the maintainer's own and is not in
    the repository, so its absence is a configuration state, not a defect.
    """
    pytest.importorskip("kirby_cost")
    path = authored_hdc(name)
    if path is None:
        pytest.skip(
            f"{name}.hdc not available — set {AUTHORED_ENV} to a directory "
            f"holding {', '.join(sorted(AUTHORED))}.hdc"
        )
    return str(path)
