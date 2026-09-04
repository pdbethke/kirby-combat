"""The Objects Table, as the book prints it (6E2 p173).

These are not tests of arithmetic. They pin TRANSCRIPTION: the numbers a
GM would read off the page. Three places in this codebase have carried a
wrong citation for this table, and the presets in use were invented
ranges rather than the book's values, so the transcription is the thing
most worth guarding.
"""
import pytest

from kirby_combat.breakables.object_table import OBJECT_DURABILITY, ObjectDurability


@pytest.mark.parametrize("kind,pd,ed,body", [
    ("brick wall", 5, 10, 3),
    ("concrete wall", 6, 10, 5),
    ("reinforced concrete wall", 8, 10, 5),
    ("wooden wall", 4, 3, 3),
    ("home inside wall", 3, 3, 3),
    ("home outside wall", 4, 6, 3),
    ("armored wall", 13, 18, 7),
    ("interior wood door", 2, 2, 3),
    ("exterior wood door", 4, 4, 3),
    ("metal fire door", 5, 5, 5),
    ("safe door", 10, 15, 9),
    ("large vault door", 16, 24, 9),
])
def test_row_matches_the_book(kind, pd, ed, body):
    row = OBJECT_DURABILITY[kind]
    assert (row.pd, row.ed, row.body) == (pd, ed, body)


def test_pd_and_ed_genuinely_differ_somewhere():
    """Guards the guard. If every row had pd == ed, the whole PD/ED split
    this plan exists for would be untestable and no caller would notice a
    selection bug."""
    assert any(r.pd != r.ed for r in OBJECT_DURABILITY.values())


def test_glass_defense_is_not_resistant():
    """6E2 p173 prints glass's defense in parentheses, which the table's
    own footnote defines as Normal Defense: it does not apply against
    Killing damage."""
    assert OBJECT_DURABILITY["glass"].resistant is False
    assert OBJECT_DURABILITY["reinforced glass"].resistant is False


def test_walls_are_resistant_by_default():
    assert OBJECT_DURABILITY["brick wall"].resistant is True


def test_keys_are_lowercase_and_values_are_whole_numbers():
    for kind, row in OBJECT_DURABILITY.items():
        assert kind == kind.lower(), kind
        assert isinstance(row, ObjectDurability)
        for field in (row.pd, row.ed, row.body):
            assert isinstance(field, int) and field >= 0, kind
