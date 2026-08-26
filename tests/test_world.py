"""World — a setting containing many Scenes."""
from kirby_combat import World
from kirby_combat.scene import Scene, SceneBounds, AmbientConditions


def _a_scene(scene_id: str, name: str = "Test Scene") -> Scene:
    """Create a minimal test scene."""
    return Scene(
        id=scene_id, name=name,
        bounds=SceneBounds(0, 0, 0, 50, 50, 20),
        surfaces=[],
        walls=[],
        hazards=[],
        ambient=AmbientConditions(),
    )


def test_a_world_holds_many_scenes():
    w = World(id="w1", name="Millennium City",
              scenes=[_a_scene("base"), _a_scene("rooftop")])
    assert [s.id for s in w.scenes] == ["base", "rooftop"]


def test_scene_by_id_returns_the_scene_when_found():
    scene = _a_scene("base")
    w = World(id="w1", name="X", scenes=[scene])
    assert w.scene_by_id("base") is scene


def test_scene_by_id_returns_none_when_absent():
    w = World(id="w1", name="X", scenes=[_a_scene("base")])
    assert w.scene_by_id("nope") is None


def test_a_world_can_be_empty():
    assert World(id="w1", name="X").scenes == []
