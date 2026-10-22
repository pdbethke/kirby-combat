"""The corpus variable's contract: unset skips, set-but-wrong FAILS.

Warp review 2026-10-20, F2: a directory of oracle-dump JSON — the
`kirby-cost/tests/fixtures/authored/*.json` files, which sit right beside
the .hdc they came from and look like build docs — was handed to
KIRBY_COMBAT_BUILDS and produced eleven failures that read as engine defects
(Bokor, Ravel and PowerLad with no frameworks). A stale variable name had
earlier left 69 real-character tests skipped. Not configuring the corpus is a
configuration state; configuring it WRONG is a defect, and it says so where
the answer is cheap — at load, by name — rather than deep in a fight.
"""
from __future__ import annotations

import json

import pytest

import tests.corpus as corpus

#: A canonical doc's top level as `to_build_json` writes it. Contents are
#: irrelevant to the shape gate, which is what these tests exercise.
CANONICAL = {
    "name": "Ravel", "template": "", "base_points": 400, "disad_points": 75,
    "experience": 0, "characteristics": [], "powers": [], "skills": [],
    "perks": [], "talents": [], "martial_arts": [], "disadvantages": [],
}
#: The oracle dump's top level: no costing header, `complications` not
#: `disadvantages`.
ORACLE_DUMP = {
    "name": "Ravel", "characteristics": [], "skills": [], "powers": [],
    "perks": [], "talents": [], "complications": [], "martial_arts": [],
}


def _corpus(tmp_path, monkeypatch, docs: dict[str, dict]):
    for name, doc in docs.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(doc))
    monkeypatch.setenv(corpus.AUTHORED_ENV, str(tmp_path))


def test_an_unset_corpus_skips(monkeypatch):
    monkeypatch.delenv(corpus.AUTHORED_ENV, raising=False)
    with pytest.raises(pytest.skip.Exception):
        corpus.require_authored_doc("Ravel")


def test_a_corpus_that_is_not_a_directory_fails(tmp_path, monkeypatch):
    monkeypatch.setenv(corpus.AUTHORED_ENV, str(tmp_path / "nowhere"))
    with pytest.raises(pytest.fail.Exception, match="not a directory"):
        corpus.require_authored_doc("Ravel")


def test_a_corpus_missing_a_cleared_character_fails_by_name(tmp_path, monkeypatch):
    _corpus(tmp_path, monkeypatch, {"Bokor": CANONICAL})
    with pytest.raises(pytest.fail.Exception, match="Ravel.json"):
        corpus.require_authored_doc("Ravel")


def test_an_oracle_dump_is_refused_by_name_not_loaded(tmp_path, monkeypatch):
    _corpus(tmp_path, monkeypatch, {"Ravel": ORACLE_DUMP})
    with pytest.raises(pytest.fail.Exception) as refused:
        corpus.require_authored_doc("Ravel")
    message = str(refused.value)
    assert "not a canonical build doc" in message
    assert "disadvantages" in message
    assert "write_build_docs.py" in message


def test_a_canonical_doc_passes_the_gate(tmp_path, monkeypatch):
    _corpus(tmp_path, monkeypatch, {"Ravel": CANONICAL})
    assert corpus.require_authored_doc("Ravel") == CANONICAL
