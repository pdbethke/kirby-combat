"""``Side`` — the object that replaced a string, and why.

As `side: str` the model had three defects a type removes:

* Two spellings became two things. ``"Golden"`` and ``"golden"`` in one
  roster made a fifth army in a four-army battle, changing who won, with
  nothing to look at. Catching it needed a canonicalising validator run
  after the fact; ``Side.named`` makes it impossible to create.
* Nothing could hang off the value --- "is this side still standing", "what
  team is it from", "is this a real side or a lone brawler" were all
  re-derived by every caller.
* The absent case had to be encoded IN the string, as a ``"solo:<id>"``
  convention every reader had to know and none could enforce.
"""
from __future__ import annotations

import pytest

from kirby_combat.side import SOLO_PREFIX, Side


# ---- Identity is the id ----

def test_two_spellings_of_one_name_are_one_side():
    """The defect that made this a class. As strings these were two armies."""
    assert Side.named("Golden") == Side.named("golden")
    assert Side.named("Golden") == Side.named("  Golden  ")
    assert Side.named("Golden Horde") == Side.named("Golden   Horde")


def test_one_side_hashes_once():
    assert len({Side.named("Golden"), Side.named("GOLDEN")}) == 1


def test_the_display_name_keeps_the_spelling_it_was_given():
    """Folding is for identity only --- a result still reports the name a
    caller wrote, not a lowercased one."""
    assert Side.named("Iron Chorus").name == "Iron Chorus"
    assert Side.named("  Iron Chorus  ").name == "Iron Chorus"


def test_different_names_are_different_sides():
    assert Side.named("Golden") != Side.named("Goldne")


def test_the_team_reference_does_not_split_a_side():
    """`team_id` is a back-reference, not part of identity: the same side
    reached two ways must still compare equal."""
    assert Side(id="golden", name="Golden") == Side(
        id="golden", name="Golden", team_id="t-42",
    )


def test_the_display_name_does_not_split_a_side():
    assert Side(id="golden") == Side(id="golden", name="The Golden Horde")


# ---- Construction ----

def test_a_side_needs_an_id():
    with pytest.raises(ValueError, match="id"):
        Side(id="   ")


def test_a_named_side_needs_a_name():
    with pytest.raises(ValueError, match="name"):
        Side.named("   ")


def test_the_name_defaults_to_the_id():
    assert Side(id="golden").name == "golden"


def test_str_is_the_display_name():
    """So an f-string in a result reads 'Iron Chorus', not a repr."""
    assert f"{Side.named('Iron Chorus')}" == "Iron Chorus"


# ---- Solo: the default that carries the design ----

def test_a_solo_side_is_unique_to_its_combatant():
    assert Side.solo("a") != Side.solo("b")
    assert Side.solo("a") == Side.solo("a")


def test_a_solo_side_is_marked_as_one():
    assert Side.solo("drifter").is_solo is True
    assert Side.named("Sentinels").is_solo is False
    assert Side.solo("drifter").id.startswith(SOLO_PREFIX)


def test_a_solo_side_reads_as_the_combatant():
    assert str(Side.solo("drifter")) == "drifter"


def test_a_named_side_cannot_be_confused_with_a_solo_one():
    """The old string convention could not enforce this at all."""
    assert Side.named("drifter") != Side.solo("drifter")
