"""A typo must not quietly become a fifth army.

`side` is a free string, which is what lets any number of sides exist
without the engine knowing them in advance. The cost is that
``"Golden"`` and ``"golden"`` are two armies, and a stray space makes a
third --- so a twelve-soldier, four-army battle silently becomes a
five-army battle that ends differently, with nothing to look at.

TWO KINDS OF TYPO, AND ONLY ONE IS CATCHABLE WITHOUT HELP:

* **Mechanical variants** --- case and whitespace. ``"Golden"``,
  ``"golden"``, ``" Golden "`` are the same word written carelessly.
  These are detectable from the roster alone: two labels that differ only
  in case or spacing are almost certainly meant to be one side.
* **Real misspellings** --- ``"Goldne"``. Nothing in the roster says this
  is wrong; only a caller who knows the intended sides can say so. That
  is what ``expected`` is for.

RAISING RATHER THAN MERGING is deliberate. Silently folding ``"golden"``
into ``"Golden"`` would fix the count and hide the defect, and would also
guess: the two labels might genuinely be meant as different sides in a
fight where someone is using case to distinguish them. The engine says
what it found and lets the caller decide.
"""
from __future__ import annotations

import pytest

from conftest import fighter, session_of  # tests/loop/conftest.py
from kirby_combat.loop.sides import (
    AmbiguousSides, UnexpectedSide, canonical_side, side_of, validate_sides,
)


# ---- canonical_side: what counts as "the same label" ----

@pytest.mark.parametrize(
    "label, expected",
    [
        ("Golden", "golden"),
        ("golden", "golden"),
        ("  Golden  ", "golden"),
        ("GOLDEN", "golden"),
        ("Golden Horde", "golden horde"),
        ("Golden   Horde", "golden horde"),
        ("Golden\tHorde", "golden horde"),
    ],
)
def test_case_and_whitespace_collapse_to_one_key(label, expected):
    assert canonical_side(label) == expected


def test_a_whitespace_only_side_is_no_side_at_all():
    """`side="   "` is truthy, so without this it would name an army of
    spaces rather than falling through to the free-for-all default."""
    assert canonical_side("   ") == ""
    assert side_of(fighter("a", side="   ")) == "solo:a"


def test_distinct_words_stay_distinct():
    assert canonical_side("Golden") != canonical_side("Goldne")


# ---- The four-army roster, clean ----

def test_a_clean_roster_validates():
    roster = [
        fighter(f"{army}-{n}", side=army)
        for army in ("Crimson", "Azure", "Verdant", "Golden")
        for n in range(3)
    ]
    validate_sides(session_of(*roster))  # does not raise


def test_a_free_for_all_validates():
    validate_sides(session_of(*[fighter(n) for n in "abcde"]))


# ---- The fifth army ----

def test_a_case_typo_is_caught_and_both_spellings_named():
    roster = [fighter("g1", side="Golden"), fighter("g2", side="golden"),
              fighter("c1", side="Crimson")]
    with pytest.raises(AmbiguousSides) as excinfo:
        validate_sides(session_of(*roster))
    message = str(excinfo.value)
    assert "Golden" in message and "golden" in message
    assert "g1" in message and "g2" in message, "name the combatants, not just the labels"


def test_a_whitespace_typo_is_caught():
    roster = [fighter("g1", side="Golden Horde"),
              fighter("g2", side="Golden  Horde")]
    with pytest.raises(AmbiguousSides, match="Golden"):
        validate_sides(session_of(*roster))


def test_a_leading_space_is_caught():
    roster = [fighter("g1", side="Golden"), fighter("g2", side=" Golden")]
    with pytest.raises(AmbiguousSides):
        validate_sides(session_of(*roster))


def test_the_error_reports_every_ambiguous_group_not_only_the_first():
    roster = [
        fighter("g1", side="Golden"), fighter("g2", side="golden"),
        fighter("c1", side="Crimson"), fighter("c2", side="CRIMSON"),
    ]
    with pytest.raises(AmbiguousSides) as excinfo:
        validate_sides(session_of(*roster))
    message = str(excinfo.value)
    assert "Golden" in message and "Crimson" in message


# ---- Real misspellings: only a declared roster can catch these ----

def test_a_misspelling_passes_without_an_expected_set():
    """Nothing in the roster says "Goldne" is wrong. Stated as a test so
    the limit is pinned rather than assumed away."""
    roster = [fighter("g1", side="Golden"), fighter("g2", side="Goldne")]
    validate_sides(session_of(*roster))  # does not raise


def test_an_expected_set_catches_a_misspelling():
    roster = [fighter("g1", side="Golden"), fighter("g2", side="Goldne")]
    with pytest.raises(UnexpectedSide) as excinfo:
        validate_sides(
            session_of(*roster),
            expected={"Crimson", "Azure", "Verdant", "Golden"},
        )
    assert "Goldne" in str(excinfo.value)
    assert "g2" in str(excinfo.value)


def test_the_expected_set_is_matched_canonically():
    """Declaring "Golden" accepts a soldier labelled "golden" --- the
    expected set is a list of sides, not a spelling test."""
    validate_sides(
        session_of(fighter("g1", side="golden")), expected={"Golden"},
    )


def test_unlabelled_combatants_are_allowed_alongside_an_expected_set():
    """A loner in a fight between declared armies is not an unexpected
    side: they were never claiming to be on one."""
    validate_sides(
        session_of(fighter("g1", side="Golden"), fighter("x")),
        expected={"Golden"},
    )


# ---- The loop calls it ----

def test_run_encounter_validates_before_the_first_phase():
    from conftest import encounter_of
    from kirby_combat.loop import FirstLegalChooser, run_encounter
    from kirby_dice import RandomRoller

    enc = encounter_of(fighter("g1", side="Golden"), fighter("g2", side="golden"))
    with pytest.raises(AmbiguousSides):
        run_encounter(enc, FirstLegalChooser(), roller=RandomRoller(seed=1))


def test_run_encounter_accepts_an_expected_set():
    from conftest import encounter_of
    from kirby_combat.loop import FirstLegalChooser, run_encounter
    from kirby_dice import RandomRoller

    enc = encounter_of(fighter("a", side="Heroes"), fighter("b", side="Villains"))
    with pytest.raises(UnexpectedSide, match="Villains"):
        run_encounter(
            enc, FirstLegalChooser(), roller=RandomRoller(seed=1),
            expected_sides={"Heroes", "Rogues"},
        )
