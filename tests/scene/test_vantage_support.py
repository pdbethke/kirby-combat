"""Support-aware vantage search (supported-vantages spec §3).

The scene is URBAN_ROOFTOP's geometry verbatim: 50x50 ground at z=0, a
rooftop tier at z=6 over the north-west, and an 8 m stone wall screening
ground<->rooftop lines of fire.
"""
import pytest

from kirby_combat.scene.scene import (
    AmbientConditions, Position, Scene, SceneBounds, Surface, Wall,
)
from kirby_combat.scene.falling import is_supported_at
from kirby_combat.scene.geometry import line_of_sight_clear
from kirby_combat.scene.movement_legality import mode_requires_support
from kirby_combat.scene.visibility import (
    _surface_candidates, nearest_hidden_point, nearest_visible_point,
)

ROOFTOP = Position(0.0, 13.0, 6.0)     # rooftop
GROUND_TARGET = Position(-10.0, -15.0, 0.0)    # ground, behind the wall


def _scene(walkable: float = 0.0) -> Scene:
    wall = Wall(
        id="stone", name="stone_wall",
        segment=(Position(-16.0, -5.0, 0.0), Position(-2.0, -5.0, 0.0)),
        height_m=8.0, walkable_width_m=walkable,
    )
    return Scene(
        id="s", name="urban_rooftop",
        bounds=SceneBounds(-25.0, -25.0, -5.0, 25.0, 25.0, 15.0),
        surfaces=[
            Surface("g", "ground",
                    [(-25.0, -25.0), (25.0, -25.0), (25.0, 25.0), (-25.0, 25.0)],
                    0.0, "ground"),
            Surface("r", "rooftop",
                    [(-25.0, 5.0), (10.0, 5.0), (10.0, 25.0), (-25.0, 25.0)],
                    6.0, "rooftop"),
        ],
        walls=[wall], hazards=[], ambient=AmbientConditions(),
    )


# ── mode_requires_support ────────────────────────────────────────────

def test_flight_and_climbing_do_not_require_a_floor():
    """whole-branch review IMPORTANT 2: climbing holds a face, not a floor —
    mode_requires_support must stop contradicting _climbing, which
    deliberately grants unsupported mid-face destinations."""
    assert mode_requires_support("flight") is False
    assert mode_requires_support("climbing") is False
    for mode in ("running", "leaping", "teleportation", "tunneling", "swimming"):
        assert mode_requires_support(mode) is True


def test_unknown_mode_conservatively_requires_support():
    assert mode_requires_support("hyperspace_shunt") is True


def test_climb_to_a_mid_face_destination_is_not_pre_filtered_by_support():
    """Consequence of IMPORTANT 2's fix: with require_support=False for
    climbing, a vantage search may hand climbing mid-air candidates.
    Pin that a genuine mid-face point (2m up an 8m climbable wall) is not
    rejected merely because nothing is under it — the real gate is
    `_climbing`, which requires the point be on a climbable face."""
    from kirby_combat.scene.falling import is_supported_at
    wall = Wall(
        id="stone", name="stone_wall",
        segment=(Position(-16.0, -5.0, 0.0), Position(-2.0, -5.0, 0.0)),
        height_m=8.0, climb_difficulty=2,
    )
    sc = Scene(
        id="s", name="urban_rooftop",
        bounds=SceneBounds(-25.0, -25.0, -5.0, 25.0, 25.0, 15.0),
        surfaces=[
            Surface("g", "ground",
                    [(-25.0, -25.0), (25.0, -25.0), (25.0, 25.0), (-25.0, 25.0)],
                    0.0, "ground"),
        ],
        walls=[wall], hazards=[], ambient=AmbientConditions(),
    )
    mid_face = Position(-9.0, -5.0, 2.0)
    # The point genuinely has nothing under it...
    assert is_supported_at(mid_face, sc) is False
    # ...but climbing does not require support, so a consumer following the
    # documented require_support=mode_requires_support(mode) pattern will
    # still offer it as a candidate for _climbing to accept or reject.
    assert mode_requires_support("climbing") is False


# ── nearest_visible_point ────────────────────────────────────────────

def test_the_start_position_really_is_occluded():
    """Guards the premise of every test below."""
    sc = _scene()
    assert nearest_visible_point(
        ROOFTOP, GROUND_TARGET, sc, radius=15.0, vertical_reach=30.0,
    ) != ROOFTOP


def test_teleporter_gets_a_supported_vantage_within_a_half_move():
    """A teleporter: 30 -> 15 m half-move, 30 m vertical reach. The
    rooftop's south-east vertex (10, 5, 6) is 12.81 m away, supported, and
    LoS-clear. This is THE case the spec exists to fix."""
    sc = _scene()
    dest = nearest_visible_point(
        ROOFTOP, GROUND_TARGET, sc, radius=15.0, vertical_reach=30.0,
        require_support=True,
    )
    assert dest is not None
    assert is_supported_at(dest, sc) is True
    assert line_of_sight_clear(dest, GROUND_TARGET, sc.walls) is True


def test_require_support_never_returns_an_unsupported_point():
    sc = _scene()
    for radius in (5.0, 15.0, 30.0):
        dest = nearest_visible_point(
            ROOFTOP, GROUND_TARGET, sc, radius=radius, vertical_reach=30.0,
            require_support=True,
        )
        if dest is not None and dest != ROOFTOP:
            assert is_supported_at(dest, sc) is True


def test_flight_may_still_take_a_mid_air_vantage():
    """require_support=False keeps the pre-existing over-the-top candidate
    available to a hovering mode."""
    sc = _scene()
    dest = nearest_visible_point(
        ROOFTOP, GROUND_TARGET, sc, radius=30.0, vertical_reach=30.0,
        require_support=False,
    )
    assert dest is not None
    assert line_of_sight_clear(dest, GROUND_TARGET, sc.walls) is True


def test_a_walkable_wall_top_enters_the_candidate_set():
    """The contract: a wall with a walkable width contributes a standable
    strip the search can choose. It does NOT have to WIN — in this scene a
    ground-level flank around the wall's end is nearer (9.67 m vs 12.42 m)
    and beating it would be the wrong answer."""
    walkable = _scene(walkable=1.0)
    cands = _surface_candidates(GROUND_TARGET, walkable, vertical_reach=30.0, radius=30.0)
    tops = [c for c in cands if c.z == pytest.approx(8.0)]
    assert tops, "a walkable wall top must be offered as a candidate"
    assert all(is_supported_at(c, walkable) for c in tops)


def test_a_wall_with_no_walkable_width_contributes_no_candidate():
    plain = _scene(walkable=0.0)
    cands = _surface_candidates(GROUND_TARGET, plain, vertical_reach=30.0, radius=30.0)
    assert not [c for c in cands if c.z == pytest.approx(8.0)]


def test_no_vantage_within_a_short_radius_returns_none():
    """A brick with a 3 m half-move has no vantage and should be told so —
    smashing through the wall is the correct answer for him."""
    sc = _scene()
    assert nearest_visible_point(
        GROUND_TARGET, ROOFTOP, sc, radius=3.0, vertical_reach=0.0,
        require_support=True,
    ) is None


# ── nearest_hidden_point ─────────────────────────────────────────────

def test_hidden_point_also_honours_require_support():
    sc = _scene()
    open_ground = Position(5.0, -15.0, 0.0)     # no wall between them
    dest = nearest_hidden_point(
        open_ground, GROUND_TARGET, sc, radius=12.0, vertical_reach=0.0,
        require_support=True,
    )
    if dest is not None and dest != open_ground:
        assert is_supported_at(dest, sc) is True


# ── vertical_reach=0.0 (running/swimming) must never offer a drop ───────
#
# `_surface_candidates`'s elevation gate ("a drop is always within reach")
# is true for flight/leaping/teleportation but false for running/swimming,
# which movement_legality gates on same_z. Offering a lower-elevation
# candidate to a runner lets it silently displace a legal same-elevation
# candidate (nearest_visible_point/nearest_hidden_point return only ONE
# candidate) — movement_reach then refuses it and the caller's fail-open
# drops the vantage offer entirely, leaving a runner worse off than before
# wall tops became standable.

def test_zero_vertical_reach_never_yields_a_drop_to_a_lower_surface():
    """Observer stands on the rooftop (z=6.0). A runner (vertical_reach=0.0)
    cannot change elevation at all, so the ground surface at z=0.0 — a
    drop — must never be offered as a candidate, even though the ground is
    always "supported" once you're on it."""
    sc = _scene()   # ground z=0.0, rooftop z=6.0
    observer = ROOFTOP   # (0.0, 13.0, 6.0), on the rooftop
    cands = _surface_candidates(observer, sc, vertical_reach=0.0, radius=30.0)
    assert cands, "expected at least the same-elevation candidate(s)"
    for c in cands:
        assert c.z == pytest.approx(observer.z), (
            f"a zero-vertical-reach mode must never be offered a drop, got z={c.z}"
        )


def test_zero_vertical_reach_still_offers_same_elevation_vantage():
    """A runner must still be able to reach a legal same-elevation
    candidate (the rooftop surface itself) when one is within radius —
    the fix must not remove same-elevation candidates along with drops."""
    sc = _scene()
    observer = ROOFTOP
    cands = _surface_candidates(observer, sc, vertical_reach=0.0, radius=30.0)
    assert any(c.z == pytest.approx(observer.z) for c in cands)
