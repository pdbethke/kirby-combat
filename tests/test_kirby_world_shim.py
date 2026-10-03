"""`kirby_combat.scene` and `kirby_combat.world` are a PERMANENT re-export of
kirby-world (0.20.0). Consumers that predate the split import these paths and
must never notice it, so the shim's promises are pinned here.
"""
import inspect

import kirby_world
import kirby_world.movement_legality


def test_the_pure_modules_are_the_same_module_objects():
    import kirby_combat.scene as pkg
    for name in ("cover", "falling", "generate", "geometry", "hazards", "scene", "visibility"):
        old = __import__(f"kirby_combat.scene.{name}", fromlist=["_"])
        assert old is getattr(kirby_world, name) or old is __import__(
            f"kirby_world.{name}", fromlist=["_"]), name
        assert getattr(pkg, name) is old


def test_world_is_one_class():
    from kirby_combat.world import World as old
    assert old is kirby_world.World


def test_the_package_surface_is_unchanged():
    import kirby_combat.scene as pkg
    assert set(pkg.__all__) == {
        "Scene", "SceneBounds", "Surface", "Wall", "Hazard", "HazardEffect",
        "Position", "AmbientConditions", "wall_top_surface", "is_climbable",
        "Construct", "ConstructEffect", "construct_from_wall", "construct_from_hazard",
        "constructs_in", "construct_from_spawn_spec", "constructs_containing",
        "ConstructEffectResult", "resolve_construct_effect", "mode_requires_support",
    }
    assert pkg.Scene is kirby_world.Scene and pkg.Position is kirby_world.Position


def test_the_session_taking_functions_keep_their_signatures():
    """The two functions whose `session` argument moved into combat. A caller
    passing `session` --- by keyword, or `constructs_in`'s positionally ---
    must still reach the fight-aware version."""
    from kirby_combat.scene.construct import constructs_in
    from kirby_combat.scene.movement_legality import movement_reach
    import kirby_combat.scene as pkg

    assert list(inspect.signature(constructs_in).parameters) == ["scene", "session"]
    assert list(inspect.signature(movement_reach).parameters) == [
        "mode", "from_pos", "to_pos", "distance_m", "scene",
        "combatant_id", "session", "teleport_ap_levels"]
    assert pkg.constructs_in is constructs_in
    # ...while every other name in those modules is the world's own.
    import kirby_combat.scene.movement_legality as ml
    assert ml.mode_requires_support is kirby_world.movement_legality.mode_requires_support


def test_placement_and_effects_moved_up_a_level():
    import kirby_combat.construct_effects as ce
    import kirby_combat.placement as pl
    from kirby_combat.scene.effects import resolve_construct_effect
    from kirby_combat.scene.placement import move_toward, position_of

    assert move_toward is pl.move_toward and position_of is kirby_world.position_of
    assert resolve_construct_effect is ce.resolve_construct_effect


def test_the_engine_itself_no_longer_imports_the_old_paths():
    """Spec gate: only the shim mentions `kirby_combat.scene` in code."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "kirby_combat"
    offenders = []
    for path in root.rglob("*.py"):
        if path.parent.name == "scene" or path.name == "world.py" and path.parent == root:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and (
                node.module == "kirby_combat.world"
                or node.module.split(".")[:2] == ["kirby_combat", "scene"]
            ):
                offenders.append(f"{path.relative_to(root.parent)}:{node.lineno}")
    assert offenders == []
