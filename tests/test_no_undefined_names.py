"""No function in this engine may reference a name that does not exist.

THE BUG THAT BOUGHT THIS TEST. `tactics/complications.py::_extract_keywords`
was carved out of the parked kirby-api with its body intact and neither of
its dependencies: `re` was never imported and `_KEYWORD_PATTERNS` was never
defined. Every call raised

    NameError: name '_KEYWORD_PATTERNS' is not defined

It sat there for the life of the module. Nothing called it, so nothing
noticed -- and a reader skimming the file would have taken it for working
code, because it reads like working code.

The suite could never have caught it: a test only fails on a line it runs,
and dead code runs nowhere. This is a STATIC check, which is the only kind
that can see an error in a function nobody calls.

IT ALSO FOUND FOUR LIVE ONES. `martial_arts` and `hero_view` each named a
real type in a forward-reference annotation that nothing imported, so the
annotation resolved to nothing for any reader or checker; `smash_cover`
(written the same day as this test) used `Any` without importing it, saved
from raising only by `from __future__ import annotations` making
annotations strings; and `resolution/damage.py` ended a function with an
unreachable `return stun, body, stun_mult` after another `return`, three
names that exist nowhere in its scope.

F821 IS THE WHOLE RULE and the list is deliberately not widened. Unused
imports (F401) and the rest are style; a name that does not exist is a
program that cannot run, and only that deserves a gate.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent / "kirby_combat"


def _ruff() -> list[str] | None:
    """Ruff as a module first, then on PATH. None when neither is there."""
    probe = subprocess.run(
        [sys.executable, "-m", "ruff", "--version"],
        capture_output=True, text=True,
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", "ruff"]
    found = shutil.which("ruff")
    return [found] if found else None


def test_no_undefined_names_anywhere_in_the_engine():
    ruff = _ruff()
    if ruff is None:
        pytest.skip("ruff is not installed; the gate runs where it is")

    result = subprocess.run(
        ruff + ["check", "--select", "F821", "--no-cache",
                "--output-format", "concise", str(ENGINE)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "a function references a name that does not exist -- it will raise "
        "NameError the moment anything calls it:\n\n" + result.stdout
    )
