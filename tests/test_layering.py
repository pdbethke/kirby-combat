"""kirby-combat may depend only on what sits BELOW it.

The dependency direction is one-way, stated by PeterB 2026-08-26: build
hierarchically; a lower module may be referenced from above, never the reverse.

**This gate is an ALLOWLIST, deliberately.** The first version was a denylist
naming the consumer it forbade — which put that consumer's name into this
package's test suite, so the package still "knew" who called it, just one file
further out. A denylist also only catches the consumers you thought of.

An allowlist states this layer's position positively: kirby-combat may import
the standard library, its own package, and its declared runtime dependencies.
Anything else is upward or sideways, and fails here whether or not anyone
anticipated it. Nothing in this file names a consumer, because it does not need
to — that is the point.

Adding a real dependency means adding it to pyproject AND to this list, which is
the intended friction: a new edge in the dependency graph should be a decision,
not a drive-by import.
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "kirby_combat"

#: This package itself.
OWN = {"kirby_combat"}

#: Declared runtime dependencies — must match pyproject's `dependencies`.
#: kirby-cost is the engine that owns build facts; anything deriving a cost,
#: a number of dice or a roll belongs there, and this package acts on the
#: numbers it is given.
DECLARED = {"kirby_cost"}

#: Modules that ship with Python. `sys.stdlib_module_names` is authoritative
#: (3.10+) and needs no hand-maintained list to drift.
STDLIB = set(sys.stdlib_module_names)

ALLOWED = OWN | DECLARED | STDLIB


def _package_files() -> list[pathlib.Path]:
    return sorted(PACKAGE.rglob("*.py"))


def _top_level_imports(path: pathlib.Path) -> set[str]:
    """Top-level component of every absolute import. Relative imports are
    intra-package by definition and cannot point upward, so they are skipped."""
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_the_package_has_files_to_check():
    """Guards the guard. If the glob broke, the test below would iterate an
    empty list and pass while checking nothing."""
    assert len(_package_files()) > 50, (
        f"expected the whole package, found {len(_package_files())} files"
    )


def test_the_allowlist_is_not_vacuous():
    """A second guard on the guard: if ALLOWED accidentally became everything
    — a stdlib set that failed to load, say — the real test could not fail."""
    assert "kirby_cost" in ALLOWED and "os" in ALLOWED
    assert "sqlalchemy" not in ALLOWED, "the allowlist has stopped excluding anything"


def test_the_engine_imports_only_what_sits_below_it():
    offenders = []
    for path in _package_files():
        for mod in sorted(_top_level_imports(path)):
            if mod not in ALLOWED:
                offenders.append(f"{path.relative_to(ROOT)}: imports {mod!r}")
    assert not offenders, (
        "kirby_combat/ may import only the standard library, itself, and its "
        "declared dependencies. An import outside that list is a dependency "
        "on a layer at or above this one:\n" + "\n".join(offenders)
    )
