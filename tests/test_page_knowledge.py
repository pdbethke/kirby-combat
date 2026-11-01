"""`CombatTemplate.page_knowledge`: what a fighter's page shows of her enemies.

"judged" is what she can reasonably judge; "sheet" is the full sheet. No
default: which one a fight runs under is the campaign's decision.
"""
from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from kirby_combat.template import (
    PAGE_KNOWLEDGE, RAW_SUPERHEROIC, TEMPLATES_BY_NAME, CombatTemplate,
)


def test_every_named_template_judges():
    assert TEMPLATES_BY_NAME
    for name in TEMPLATES_BY_NAME:
        assert CombatTemplate.by_name(name).page_knowledge == "judged"


def test_the_choices_are_judged_and_sheet():
    assert PAGE_KNOWLEDGE == frozenset({"judged", "sheet"})


def test_page_knowledge_has_no_default():
    fields = {k: v for k, v in asdict(RAW_SUPERHEROIC).items() if k != "page_knowledge"}
    with pytest.raises(TypeError):
        CombatTemplate(**fields)


def test_an_unknown_value_is_refused():
    with pytest.raises(ValueError, match="judged"):
        replace(RAW_SUPERHEROIC, page_knowledge="everything")


def test_sheet_is_accepted():
    assert replace(RAW_SUPERHEROIC, page_knowledge="sheet").page_knowledge == "sheet"
