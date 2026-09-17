"""A stored fight names its rules, and an unknown name is an error.

A consumer that persists a fight persists which campaign switches it was
run under -- as a name, because a name is the smallest thing it can keep.
`by_name` is where that name becomes a `CombatTemplate`, and the only
interesting thing about it is what it does with a name it does not know.
"""
from __future__ import annotations

import pytest

from kirby_combat.template import (
    RAW_HEROIC, RAW_SUPERHEROIC, TEMPLATES_BY_NAME, CombatTemplate,
)


def test_the_superheroic_name_is_the_default_template():
    assert CombatTemplate.by_name("6e-superheroic") is \
        CombatTemplate.default_6e_superheroic()
    assert CombatTemplate.by_name("6e-superheroic") is RAW_SUPERHEROIC


def test_the_heroic_name_is_the_heroic_template():
    """Not the same fight: hit locations on, END tracked (6E2 p.100/p.128)."""
    heroic = CombatTemplate.by_name("6e-heroic")
    assert heroic is RAW_HEROIC
    assert heroic.use_hit_locations and heroic.manage_endurance
    assert not RAW_SUPERHEROIC.use_hit_locations


def test_an_unknown_name_raises_and_says_what_it_knows():
    """No default, deliberately.

    A default would mean a consumer that lost the name silently ran the
    fight under Superheroic switches and reported the result as though
    those had been the campaign's rules all along.
    """
    with pytest.raises(KeyError) as excinfo:
        CombatTemplate.by_name("nope")

    message = str(excinfo.value)
    assert "nope" in message
    for known in TEMPLATES_BY_NAME:
        assert known in message


def test_by_name_takes_no_default_argument():
    """The refusal is the feature, so it must not be optional."""
    with pytest.raises(TypeError):
        CombatTemplate.by_name()  # type: ignore[call-arg]
