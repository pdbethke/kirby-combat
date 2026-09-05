"""The Objects Table lives in kirby-terrain, and this package re-exports it.

The table used to be defined here. It moved to `kirby-terrain` — the leaf
that owns what terrain IS — because a transcribed rulebook table with two
homes is exactly the drift this codebase has a history of: "5 STR to the
die" once lived in three places across two repositories, agreeing only by
luck.

So this file no longer tests the CONTENTS of the table. kirby-terrain's own
suite pins all 18 rows against the book. What is tested here is the one
thing that could still go wrong from this side: that `kirby_combat`'s name
and `kirby_terrain`'s name are the SAME OBJECT, so a second copy cannot
quietly reappear.
"""
import kirby_terrain

from kirby_combat import OBJECT_DURABILITY, ObjectDurability


def test_the_table_is_kirby_terrains_table_not_a_copy():
    """Identity, not equality. Two dicts that merely compare equal today
    are two tables, and the point of the move was to have one."""
    assert OBJECT_DURABILITY is kirby_terrain.OBJECT_DURABILITY


def test_the_dataclass_is_kirby_terrains_too():
    assert ObjectDurability is kirby_terrain.ObjectDurability


def test_this_package_no_longer_defines_its_own_table():
    """Guards the guard. If someone re-adds `breakables/object_table.py`,
    the identity test above would still pass while `kirby_combat` quietly
    shipped a second definition for anything importing the deep path."""
    import importlib

    try:
        importlib.import_module("kirby_combat.breakables.object_table")
    except ModuleNotFoundError:
        return
    raise AssertionError(
        "kirby_combat.breakables.object_table exists again — the Objects "
        "Table has one home, and it is kirby_terrain.durability"
    )


def test_the_re_exported_table_still_answers_correctly():
    """A thin sanity check that the re-export is wired, without duplicating
    kirby-terrain's row-by-row transcription tests."""
    brick = OBJECT_DURABILITY["brick wall"]
    assert (brick.pd, brick.ed, brick.body, brick.resistant) == (5, 10, 3, True)
