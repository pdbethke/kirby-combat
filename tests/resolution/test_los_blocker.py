"""LoS returns which wall first blocks a shot (spec §1.3)."""
from kirby_combat.scene import Scene, SceneBounds, Wall, Position, AmbientConditions
from kirby_combat.resolution.line_of_sight import blocking_wall_for_shot


def _scene(walls):
    return Scene(id="s", name="n",
                 bounds=SceneBounds(min_x=-20, min_y=-20, min_z=0, max_x=20, max_y=20, max_z=10),
                 surfaces=[], walls=walls, hazards=[], ambient=AmbientConditions())


def _wall(wid, x):
    return Wall(id=wid, name=wid, segment=(Position(x, -5, 0), Position(x, 5, 0)),
                height_m=3.0, blocks_los=True, blocks_movement=True, cover_level=4, body=8)


def test_blocking_wall_returned():
    s = _scene([_wall("near", -3), _wall("far", 3)])
    w = blocking_wall_for_shot(s, Position(-10, 0, 0), Position(10, 0, 0), is_ranged=True)
    assert w is not None and w.id == "near"


def test_clear_shot_no_blocker():
    s = _scene([])
    assert blocking_wall_for_shot(s, Position(-10, 0, 0), Position(10, 0, 0), is_ranged=True) is None


def test_hth_attack_never_blocked():
    s = _scene([_wall("near", 0)])
    assert blocking_wall_for_shot(s, Position(-1, 0, 0), Position(1, 0, 0), is_ranged=False) is None
