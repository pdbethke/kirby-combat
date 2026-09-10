"""The page lists men one by one and never says what shape they are in.

A point-of-view render of the same moment was shown to a vision model,
which reported four things: six figures, solid walls both flanks, open
ground between, and "they are tightly bunched together".

Three of those the Brief already says, more precisely. The fourth it
NEVER says. Its "Where they are" section is a list:

    The Kid:    46.0m, -6 OCV at that range, cover 2/4
    Rell Hoyt:  46.3m, -6 OCV at that range
    Beck:       49.2m, -6 OCV at that range, cover 2/4

Exact, and silent about the shape. "Bunched" is the fact that makes an
Area Of Effect, a Sweep or a group Presence Attack worth taking, and it
is exactly what a picture gives away for free and a list of distances
does not.

So compute it. Whether stating it CHANGES anything is a separate
question and the reason `coverage.py` exists --- two Brief improvements
predicted to help this week moved nothing.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from kirby_combat.scene.scene import Position
from kirby_combat.formation import Formation, formation_of


def _at(*pairs):
    return [Position(x, y, 0.0) for x, y in pairs]


class TestHowSpreadOutTheyAre:
    def test_men_standing_on_each_other_are_bunched(self):
        f = formation_of(_at((0, 0), (1, 0), (0.5, 1)))
        assert f.spread_m < 2.0
        assert f.is_bunched is True

    def test_men_across_a_street_are_not(self):
        f = formation_of(_at((0, 0), (20, 0), (40, 5)))
        assert f.spread_m > 20
        assert f.is_bunched is False

    def test_spread_is_the_widest_gap_between_any_two(self):
        """Not the average, which hides a straggler: four men in a knot
        and one forty metres off is NOT a bunch, and an Area Of Effect
        aimed at the knot does not reach him."""
        f = formation_of(_at((0, 0), (1, 0), (2, 0), (40, 0)))
        assert f.spread_m == 40.0
        assert f.is_bunched is False


class TestOneManAndNone:
    def test_a_lone_enemy_has_no_formation(self):
        """One man is not a shape, and 'bunched' about him is nonsense."""
        assert formation_of(_at((3, 4))) is None

    def test_no_enemies_at_all_is_no_formation(self):
        assert formation_of([]) is None


class TestWhatItSaysOnThePage:
    def test_a_bunch_reads_as_one(self):
        line = formation_of(_at((0, 0), (1, 0), (0.5, 1))).render()
        assert "bunched" in line.lower(), line
        assert "3" in line, line

    def test_and_says_how_wide_so_a_radius_can_be_judged(self):
        """An Area Of Effect is bought in metres of radius. "Bunched" with
        no number cannot be matched against one."""
        line = formation_of(_at((0, 0), (1, 0), (0.5, 1))).render()
        assert "m" in line, line

    def test_a_scattered_line_says_so_too(self):
        """Both answers are useful: scattered is the reason NOT to spend a
        Phase on an area attack."""
        line = formation_of(_at((0, 0), (20, 0), (40, 5))).render()
        assert "spread" in line.lower() or "scattered" in line.lower(), line


class TestTheThresholdIsGrounded:
    def test_bunched_means_inside_a_typical_area_of_effect(self):
        """6E1's Area Of Effect is bought per metre of radius, and the
        common small buy is a few metres. The line exists to answer "would
        one attack catch several of them", so the threshold is that, not a
        number chosen for feel."""
        assert Formation.BUNCHED_WITHIN_M == 8.0
