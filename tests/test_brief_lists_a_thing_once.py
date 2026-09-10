"""A wagon is one wagon on the page, not four planks.

`Furnishing` projects its footprint into wall segments so that movement,
line of sight, cover moves and Area Of Effect keep working -- they all
read `scene.walls`. `Brief.features` reads `scene.walls` too, and it was
never told the difference, so a Brief listed:

    Photographer's wagon: 2.7m away, would give you cover 2/4
    Photographer's wagon: 1.6m away, would not shield you from where they are
    Photographer's wagon: 3.1m away, would give you cover 2/4
    Photographer's wagon: 4.1m away, would not shield you from where they are

Four entries for one wagon, at four distances, contradicting each other
about whether it is worth hiding behind -- because each is a different
EDGE of the same footprint and an edge on the far side genuinely does not
shield you.

A reader cannot act on that, and the page is what a chooser acts on. The
whole object is one feature: the nearest edge is how far away it is, and
the best cover any edge offers is what it is worth.

Introduced by the footprint change on 2026-09-10 and caught by reading
the page a model actually gets.
"""
from __future__ import annotations

from kirby_combat.brief import Brief


def _page():
    from examples.the_shootout_we_can_publish import the_fight

    pages: list[str] = []

    class Peek:
        def choose(self, situation):
            if not pages:
                pages.append(situation.brief().render())
            return situation.menu[0].action_id

    the_fight(59, chooser=Peek())
    return pages[0]


def _feature_lines(page: str) -> list[str]:
    out, seen = [], False
    for line in page.splitlines():
        if line.startswith("What is around you:"):
            seen = True
            continue
        if seen:
            if not line.startswith("  "):
                break
            out.append(line.strip())
    return out


def test_each_thing_appears_once():
    lines = _feature_lines(_page())
    names = [line.split(":")[0] for line in lines]
    duplicated = {n for n in names if names.count(n) > 1}
    assert not duplicated, f"listed more than once: {sorted(duplicated)}"


def test_the_wagon_is_still_there():
    """Deduplicating must not delete the thing."""
    names = [line.split(":")[0] for line in _feature_lines(_page())]
    assert any("wagon" in n.lower() for n in names), names


def test_a_thing_is_worth_the_best_cover_any_of_it_offers():
    """One edge of a wagon faces away and shields nobody; standing behind
    the wagon means standing behind the edge that does. Reporting the
    useless edge would tell a reader the wagon is worthless."""
    lines = _feature_lines(_page())
    wagon = next(line for line in lines if "wagon" in line.lower())
    assert "would give you cover" in wagon, wagon


def test_a_buildings_named_faces_are_NOT_folded_together():
    """Only the DERIVED edges fold. A furnishing's four edges were never
    authored -- they are one object's outline. A building's faces were:
    somebody wrote "C.S. Fly's boarding house (west wall)" and "C.S. Fly's
    photograph gallery" as separate walls because a fighter relates to
    them separately, and folding by `part_of` deleted the gallery from the
    page entirely."""
    names = [line.split(":")[0] for line in _feature_lines(_page())]
    assert any("gallery" in n.lower() for n in names), names
    assert any("boarding house" in n.lower() for n in names), names
