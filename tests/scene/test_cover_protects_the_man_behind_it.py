"""Cover belongs to whoever is behind it.

6E2 p.45: "Targets who are partly Behind Cover are harder to hit. The less
of the target that can be perceived and targeted, the worse the attacker's
OCV penalty." It is a statement about how much of the TARGET the shooter
can see.

`compute_cover_level` collected every wall that intersected the line of
sight and then picked the one nearest the target. A wall standing at the
SHOOTER's feet is on that line too, and when it is the only wall it is
also, trivially, the nearest one to the target -- so the shooter's own
cover was credited to the man he was shooting at.

Measured at the O.K. Corral. Doc Holliday takes cover behind the wagon,
which is the only cover anybody uses in the whole fight, and he is the
only man in it who ever pays a cover penalty: -2 OCV on both his shots,
with `target_cover_level=2` recorded against Frank and Tom, who are
standing in the open. Nobody shooting AT Doc paid anything.

So taking cover was strictly harmful --- it cost you two OCV and bought
you nothing --- and every tactic that valued cover valued it backwards.
The book's own example is the other way round: Andarra "ducks behind a
rock before firing. The well-trained Marines return fire. Because the
rock protects roughly half of Andarra, the Marines suffer a -2 OCV."

Example paraphrased; this project ships no rules text.
"""
from __future__ import annotations

from kirby_combat.scene.cover import compute_cover_level
from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)


def _lot(wall_x: float) -> Scene:
    """A shooter at x=0, a target at x=10, and one low wall between."""
    return Scene(
        id="lot", name="lot", bounds=SceneBounds(-20, -20, 0.0, 20, 20, 10.0),
        surfaces=[Surface(id="g", name="g",
                          polygon_xy=[(-20, -20), (20, -20), (20, 20), (-20, 20)],
                          elevation_m=0.0, surface_type="ground", cover_level=0)],
        walls=[Wall(id="wagon", name="Wagon",
                    segment=(Position(wall_x, -2.0, 0.0),
                             Position(wall_x, 2.0, 0.0)),
                    height_m=1.5, cover_level=2, body=12, def_value=3)],
        hazards=[], ambient=AmbientConditions(light_level=4),
        combatant_positions={},
    )


SHOOTER = Position(0.0, 0.0, 0.0)
TARGET = Position(10.0, 0.0, 0.0)


def test_a_wall_at_the_targets_end_is_the_targets_cover():
    """He is behind it, so less of him can be seen."""
    assert compute_cover_level(
        shooter_pos=SHOOTER, target_pos=TARGET,
        target_is_prone_or_diving=False, scene=_lot(wall_x=9.0),
    ) == 2


def test_a_wall_at_the_shooters_end_is_not():
    """The shooter is behind it. It hides HIM, and hides nothing of the
    man he is aiming at -- he simply fires over it, which is what the
    book's Andarra does."""
    assert compute_cover_level(
        shooter_pos=SHOOTER, target_pos=TARGET,
        target_is_prone_or_diving=False, scene=_lot(wall_x=1.0),
    ) == 0


def test_a_wall_in_the_middle_still_counts_for_the_target():
    """Being obscured is a matter of degree, and the far half of the line
    is the half that obscures. The midpoint is the boundary and belongs
    to the target: a wall exactly between two men blocks each of them
    from the other."""
    assert compute_cover_level(
        shooter_pos=SHOOTER, target_pos=TARGET,
        target_is_prone_or_diving=False, scene=_lot(wall_x=5.0),
    ) == 2


def test_the_rule_is_symmetric():
    """Turn the shot around and the same wagon changes hands. If it did
    not, the pair of them would both be in cover or neither would."""
    scene = _lot(wall_x=1.0)
    theirs = compute_cover_level(
        shooter_pos=TARGET, target_pos=SHOOTER,
        target_is_prone_or_diving=False, scene=scene)
    mine = compute_cover_level(
        shooter_pos=SHOOTER, target_pos=TARGET,
        target_is_prone_or_diving=False, scene=scene)
    assert (theirs, mine) == (2, 0)
