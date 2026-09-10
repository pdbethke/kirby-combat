"""A wagon is a footprint, not a line.

Scenery in this engine has only ever been a `Wall`: a SEGMENT and a
height. That is the right model for the side of a building and the wrong
one for everything you can walk around — a wagon, a stack of barrels, a
crate pile, a boulder, a parked car.

Three things went wrong at once because of it, all measured on the O.K.
Corral board:

  * THE RENDERER GUESSES. `wallToBox` draws every wall 0.4 m thick, a
    constant with nothing behind it, because a line has no width to read.
    A wagon drawn 0.4 m across reads as a plank.
  * MEN STAND INSIDE THE FURNITURE. Nothing stops them: a line occupies
    no ground. Wyatt is 0.40 m from the wagon's line, Virgil 0.50, Morgan
    0.82 — all three inside a wagon of any realistic width.
  * COVER IS A GUESS TOO. `cover_level` is authored by hand per wall
    because nothing knows what the thing is made of, while
    `kirby_terrain.OBJECT_DURABILITY` — 6E2 p.173's own Objects Table —
    has been sitting there carrying DEF and BODY for eighteen materials.

A footprint fixes all three from one fact, which is why it is one change
and not three.

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

import pytest

from kirby_combat.scene.scene import Furnishing

#: A two-by-four-metre wagon bed, corners CCW.
WAGON = Furnishing(
    id="wagon", name="Wagon",
    polygon_xy=[(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)],
    height_m=1.5, material="wooden wall",
)


class TestTheGroundItStandsOn:
    def test_a_point_inside_the_footprint_is_occupied(self):
        assert WAGON.occupies(2.0, 1.0) is True

    def test_a_point_outside_it_is_not(self):
        assert WAGON.occupies(5.0, 1.0) is False
        assert WAGON.occupies(2.0, 3.0) is False

    def test_the_footprint_has_a_real_width(self):
        """The whole point: a line has none, so the renderer invented one
        and placement had nothing to refuse."""
        assert WAGON.width_m == pytest.approx(2.0)
        assert WAGON.length_m == pytest.approx(4.0)

    def test_it_knows_where_it_stands(self):
        assert WAGON.centre_xy == pytest.approx((2.0, 1.0))


class TestWhatItIsMadeOf:
    def test_durability_comes_from_the_objects_table(self):
        """6E2 p.173, via `kirby_terrain.OBJECT_DURABILITY`. Nobody should
        be typing a wagon's BODY into a scene file by hand."""
        assert (WAGON.pd_value, WAGON.ed_value, WAGON.body_value) == (4, 3, 3)

    def test_an_explicit_figure_beats_the_table(self):
        """6E2 p.172 says the table is a baseline a GM should change to
        fit the adventure, so an override is the rule and not a hack."""
        armoured = Furnishing(
            id="w", name="Armoured wagon",
            polygon_xy=WAGON.polygon_xy, height_m=1.5,
            material="wooden wall", body=20,
        )
        assert armoured.body_value == 20
        assert armoured.pd_value == 4, "the rest still comes from the table"

    def test_a_thing_the_table_has_no_row_for_must_say_its_own_numbers(self):
        """The table is walls, doors and glass. It has no wagon, no
        barrel and no tree, and inventing a row would be worse than
        asking."""
        with pytest.raises(ValueError, match="material"):
            Furnishing(id="x", name="Oak", polygon_xy=WAGON.polygon_xy,
                       height_m=6.0)

    def test_naming_a_material_that_does_not_exist_is_refused(self):
        with pytest.raises(ValueError, match="unicorn hide"):
            Furnishing(id="x", name="X", polygon_xy=WAGON.polygon_xy,
                       height_m=1.0, material="unicorn hide")


class TestWhatItDoesToASightLine:
    def test_something_you_can_see_over_does_not_block_sight(self):
        """A 1.5 m wagon is chest height on a standing man, which is why
        he can shoot over it — and why it is cover rather than a wall."""
        assert WAGON.blocks_los is False

    def test_something_taller_than_a_man_does(self):
        stack = Furnishing(id="s", name="Crate stack", polygon_xy=WAGON.polygon_xy,
                           height_m=2.4, material="wooden wall")
        assert stack.blocks_los is True

    def test_the_author_can_say_otherwise(self):
        """A thicket is taller than a man and you can see through it."""
        thicket = Furnishing(id="t", name="Thicket", polygon_xy=WAGON.polygon_xy,
                             height_m=2.4, material="wooden wall",
                             blocks_los_override=False)
        assert thicket.blocks_los is False


# ---------------------------------------------------------------------------
# What it changes. A type nothing consults is scenery for the reader.
# ---------------------------------------------------------------------------
from kirby_combat.scene.scene import (           # noqa: E402
    AmbientConditions, Position, Scene, SceneBounds, Surface,
)


def _lot(furnishings) -> Scene:
    return Scene(
        id="lot", name="lot", bounds=SceneBounds(-20, -20, 0.0, 20, 20, 10.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-20, -20), (20, -20), (20, 20), (-20, 20)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[], hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={}, furnishings=list(furnishings),
    )


class TestYouCannotStandInsideIt:
    def test_the_scene_says_the_ground_is_taken(self):
        """The question a line could never answer."""
        from kirby_combat.scene.placement import blocked_by_furnishing

        scene = _lot([WAGON])
        assert blocked_by_furnishing(scene, Position(2.0, 1.0, 0.0)) is WAGON
        assert blocked_by_furnishing(scene, Position(6.0, 1.0, 0.0)) is None

    def test_something_you_can_walk_through_does_not_block(self):
        from kirby_combat.scene.placement import blocked_by_furnishing

        smoke = Furnishing(id="s", name="Smoke", polygon_xy=WAGON.polygon_xy,
                           height_m=2.0, pd=0, ed=0, body=1,
                           blocks_movement=False)
        assert blocked_by_furnishing(_lot([smoke]), Position(2.0, 1.0, 0.0)) is None

    def test_standing_on_the_roof_of_it_is_not_standing_in_it(self):
        """A man on top of a wagon is above its height, not inside it ---
        the same distinction `supporting_surfaces` already draws for wall
        tops."""
        from kirby_combat.scene.placement import blocked_by_furnishing

        assert blocked_by_furnishing(
            _lot([WAGON]), Position(2.0, 1.0, 1.5)) is None


class TestItGivesCover:
    def test_a_wagon_between_two_men_covers_the_far_one(self):
        from kirby_combat.scene.cover import compute_cover_level

        level = compute_cover_level(
            shooter_pos=Position(2.0, -4.0, 0.0),
            target_pos=Position(2.0, 6.0, 0.0),
            target_is_prone_or_diving=False, scene=_lot([WAGON]),
        )
        assert level == 2

    def test_and_not_the_near_one(self):
        """The rule this session already fixed for walls, holding for a
        footprint: cover belongs to whoever is behind it."""
        from kirby_combat.scene.cover import compute_cover_level

        near = Furnishing(id="w", name="Wagon",
                          polygon_xy=[(0.0, -3.5), (4.0, -3.5),
                                      (4.0, -1.5), (0.0, -1.5)],
                          height_m=1.5, material="wooden wall")
        level = compute_cover_level(
            shooter_pos=Position(2.0, -4.0, 0.0),
            target_pos=Position(2.0, 6.0, 0.0),
            target_is_prone_or_diving=False, scene=_lot([near]),
        )
        assert level == 0


class TestYouCanShootIt:
    def test_it_is_something_an_attack_can_be_aimed_at(self):
        """`constructs_in` is what `attack_construct` enumerates. A wagon
        nothing can shoot is a wagon nobody can shoot the cover out from
        under --- which is exactly the tactic `smash_cover` exists for."""
        from kirby_combat.scene.construct import constructs_in

        ids = {c.obj_id for c in constructs_in(_lot([WAGON]))}
        assert "wagon" in ids

    def test_it_arrives_with_the_books_own_durability(self):
        from kirby_combat.scene.construct import constructs_in

        wagon = next(c for c in constructs_in(_lot([WAGON]))
                     if c.obj_id == "wagon")
        assert wagon.body == 3       # wooden wall, 6E2 p173


# ---------------------------------------------------------------------------
# It has to work with everything that already reads `scene.walls`
# ---------------------------------------------------------------------------
class TestItProjectsIntoWalls:
    """Twelve modules ask `scene.walls` about movement, line of sight,
    visibility, cover moves, collapse, knockback and Area Of Effect.
    Authoring a wagon as a Furnishing and stopping there would silently
    REMOVE all of that — you could walk through it, nobody could take
    cover behind it, and it would not stop a blast.

    So a footprint projects into the wall segments its edges already are.
    The same move `constructs_in` makes in the other direction, and its
    own words for it: "a second VIEW of the same geometry rather than a
    second copy of it".
    """

    def test_a_footprint_becomes_its_edges(self):
        walls = WAGON.as_walls()
        assert len(walls) == 4, "a rectangle has four sides"

    def test_the_edges_carry_the_furnishings_own_facts(self):
        wall = WAGON.as_walls()[0]
        assert wall.height_m == WAGON.height_m
        assert wall.cover_level == WAGON.cover_level
        assert wall.body == WAGON.body_value
        assert wall.def_value == WAGON.pd_value
        assert wall.blocks_los is WAGON.blocks_los

    def test_every_edge_says_which_thing_it_belongs_to(self):
        """`part_of` already means "this is a face of that structure",
        and it is what stops a shot at one plank destroying the wagon."""
        assert all(w.part_of == "wagon" for w in WAGON.as_walls())

    def test_the_scene_projects_them_without_being_asked(self):
        """An author who has to remember is an author who will forget,
        and forgetting means a wagon nothing can bump into."""
        scene = _lot([WAGON])
        assert [w.id for w in scene.walls if w.part_of == "wagon"]

    def test_projecting_twice_does_not_double_the_wagon(self):
        """`dataclasses.replace` rebuilds a Scene on every move anybody
        makes, so this runs constantly."""
        from dataclasses import replace

        scene = _lot([WAGON])
        again = replace(scene, name="lot again")
        assert len([w for w in again.walls if w.part_of == "wagon"]) == 4

    def test_an_authored_wall_is_left_alone(self):
        from kirby_combat.scene.scene import Wall

        fence = Wall(id="fence", name="Fence",
                     segment=(Position(-5, -5, 0), Position(-5, 5, 0)),
                     height_m=1.2, cover_level=2, body=4, def_value=2)
        scene = Scene(
            id="s", name="s", bounds=SceneBounds(-20, -20, 0, 20, 20, 10),
            surfaces=[], walls=[fence], hazards=[],
            ambient=AmbientConditions(light_level=4),
            furnishings=[WAGON],
        )
        assert "fence" in {w.id for w in scene.walls}
        assert len(scene.walls) == 5
