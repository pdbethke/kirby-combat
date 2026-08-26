"""Executes every script in `examples/` end-to-end and asserts it completes.

Nothing else covers this directory: pytest's `testpaths = ["tests"]` never
imports or runs `examples/`, so a script there can silently bit-rot behind a
fully green suite. This is what let `examples/rooftop_brawl.py` (and its
three siblings) break under Task 1's `StatBlockCombatant.int_` field going
non-defaulted -- three subsequent reviews missed it because nothing ran the
file. This test is deliberately dumb: it just executes each script as a
subprocess and checks the exit code and that nothing landed on stderr,
so a future signature change here gets caught the same way.
"""
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_EXAMPLES_DIR = _REPO_ROOT / "examples"
_EXAMPLE_SCRIPTS = sorted(_EXAMPLES_DIR.glob("*.py"))


@pytest.mark.parametrize(
    "script", _EXAMPLE_SCRIPTS, ids=[p.name for p in _EXAMPLE_SCRIPTS]
)
def test_example_runs_to_completion(script: pathlib.Path):
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"{script.name} exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert result.stderr == "", f"{script.name} wrote to stderr:\n{result.stderr}"


def test_examples_directory_is_not_empty():
    """Guards against this test silently covering nothing if the directory
    gets renamed/moved."""
    assert _EXAMPLE_SCRIPTS, "no example scripts found under examples/"
