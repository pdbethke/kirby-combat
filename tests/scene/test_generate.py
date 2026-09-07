"""Arena generation — terrain creation, in the engine.

CARVED OUT OF THE WRAPPER. This was 254 lines in the parked kirby-api
(`combat/random_fight/terrain.py`) whose own docstring argued for the move:
"PURE: given the same `random.Random` this returns the same arena, and it
touches neither the database nor the clock." Its entire import list was
math, random and dataclasses.

It now builds a real `Scene` rather than a dict payload, because the Scene
is what the loop, enumeration, cover and line of sight all consume.
"""
from __future__ import annotations

import math
import random

from kirby_combat.scene.generate import (
    ArenaUnplaceable, _near_segment, arena_for, generate_arena,
)
from kirby_combat.scene.scene import Scene


def _arena(seed: int = 1234, fighters: int = 8):
    return generate_arena(random.Random(seed), fighter_count=fighters)


# ---- Deterministic ----

def test_the_same_seed_builds_the_same_arena():
    """What makes a generated fight reproducible."""
    a, b = _arena(7), _arena(7)
    assert a.name == b.name
    assert a.start_positions == b.start_positions
    assert [w.id for w in a.scene.walls] == [w.id for w in b.scene.walls]


def test_different_seeds_build_different_arenas():
    assert _arena(1).name != _arena(2).name


# ---- It builds an engine Scene, not a payload ----

def test_it_returns_a_real_scene():
    """The engine's own type -- anything else means every caller converts
    before it can fight on the result."""
    arena = _arena()
    assert isinstance(arena.scene, Scene)
    assert arena.scene.surfaces and arena.scene.walls


def test_the_scene_is_usable_by_the_rules_that_read_terrain():
    from kirby_combat.scene.cover import compute_cover_level
    from kirby_combat.scene.scene import Position

    scene = _arena().scene
    assert compute_cover_level(
        shooter_pos=Position(0.0, 0.0, 0.0), target_pos=Position(5.0, 0.0, 0.0),
        target_is_prone_or_diving=False, scene=scene,
    ) >= 0


# ---- The finding this file carries ----

def test_a_meaningful_share_of_walls_are_low_cover():
    """AN ARENA WHERE EVERY WALL BLOCKS SIGHT PRODUCES A FIGHT ABOUT THE
    WALLS. Measured on the first version: 18 of 37 actions were
    `attack_construct` -- the AI saying "I must destroy the intervening
    wall to clear a path". That was GOOD PLAY AGAINST A BAD ARENA, not bad
    play: combat perception governs targeting, so fighters who cannot see
    each other correctly breach instead.

    Roughly 40% low cover is the fix, asserted across many seeds rather
    than in one lucky arena.
    """
    walls = [w for seed in range(40) for w in _arena(seed).scene.walls]
    low = [w for w in walls if not w.blocks_los]
    assert 0.25 < len(low) / len(walls) < 0.55, (
        f"{len(low)}/{len(walls)} low -- an all-blocking arena makes the "
        f"fight about breaching"
    )


def test_every_wall_is_destructible():
    """'Smash the cover' is a tactic. An absent def_value reads as
    indestructible to the engine."""
    for w in (w for seed in range(15) for w in _arena(seed).scene.walls):
        assert w.def_value is not None and w.def_value > 0
        assert w.body > 0


def test_climb_difficulty_follows_from_height():
    """6E1 p.70. Rolled independently it produced 0.9m parapets needing
    trained climbing and 9m sheer faces you could scramble untrained."""
    for w in (w for seed in range(20) for w in _arena(seed).scene.walls):
        if w.height_m <= 1.5:
            assert w.climb_difficulty == 0, "waist-high cover is vaulted"
        elif w.height_m > 7.0:
            assert w.climb_difficulty == -3, "a storey of sheer wall is not"


# ---- Start positions ----

def test_every_fighter_gets_a_start_position():
    for n in (2, 5, 8, 12):
        assert len(_arena(3, n).start_positions) == n


def test_fighters_open_apart_rather_than_on_top_of_each_other():
    """Circle placement is what guarantees it."""
    starts = _arena(11, 6).start_positions
    closest = min(
        math.dist(a[:2], b[:2])
        for i, a in enumerate(starts) for b in starts[i + 1:]
    )
    assert closest > 3.0, f"two fighters started {closest:.1f}m apart"


def test_nobody_starts_inside_a_wall():
    for seed in range(25):
        arena = _arena(seed, 8)
        for x, y, _z in arena.start_positions:
            for w in arena.scene.walls:
                assert not _near_segment(
                    (x, y), (w.segment[0].x, w.segment[0].y),
                    (w.segment[1].x, w.segment[1].y),
                ), f"seed {seed}: a fighter started inside {w.id}"


def test_the_arena_grows_with_the_roster():
    """A fixed arena crowds eight fighters and strands two."""
    assert _arena(5, 12).scene.bounds.max_x > _arena(5, 2).scene.bounds.max_x


def test_placement_failure_is_named_rather_than_silent():
    """`ArenaUnplaceable` exists so a caller learns the ARENA was the
    problem, not the roster."""
    assert issubclass(ArenaUnplaceable, RuntimeError)


# ---- The convenience ----

def test_arena_for_puts_the_combatants_on_the_ground():
    class _C:
        def __init__(self, i):
            self.id = f"f{i}"

    scene = arena_for(random.Random(9), [_C(i) for i in range(4)])
    assert set(scene.combatant_positions) == {"f0", "f1", "f2", "f3"}
