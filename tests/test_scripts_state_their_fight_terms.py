"""Every script that runs a fight states its terms (0.40.0, `FightTermsMissing`).

0.40.0 made a fight with no terms refuse to step. The examples were brought
along; `scripts/telemetry.py` and `scripts/coverage.py` were not, and nothing
noticed because they need licensed build docs CI does not have. The model
benchmark (`kirby-ai/scripts/the_corral_deliberates.py`) builds its fight
through telemetry, so it died on its first Phase the day 0.40.0 shipped.

A source scan, because these scripts cannot run here: a file that drives a
fight must also state terms.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DRIVES = ("run_encounter(", "run_phase(")
#: Stating them, or handing them to a builder that does (`terms=`).
STATES = ("state_terms(", "terms_stated(", "terms=")


def _scripts():
    for folder in ("scripts", "examples"):
        for path in sorted((ROOT / folder).glob("*.py")):
            text = path.read_text()
            if any(d in text for d in DRIVES):
                yield pytest.param(path, id=f"{folder}/{path.name}")


@pytest.mark.parametrize("path", list(_scripts()))
def test_a_script_that_runs_a_fight_states_its_terms(path):
    text = path.read_text()
    assert any(s in text for s in STATES), (
        f"{path.name} runs a fight but never states its terms; 0.40.0 refuses "
        "to step it (FightTermsMissing)")
