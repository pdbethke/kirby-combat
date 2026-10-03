"""PERMANENT re-export of kirby-world. Not deprecated, not on a clock.

The setting hierarchy moved to its own package at 0.20.0 (spec
2026-08-28-kirby-world-module-design.md). Places live in `kirby_world`; this
package exists so that every `kirby_combat.scene...` import written before the
move --- in this repo's tests, in its consumers --- keeps working untouched.

New code imports `kirby_world` directly. Two submodules are not pure
aliases, because the functions people imported from them took a fight's
`session`; those now live in combat and are re-exported here with the same
signatures:

  construct.constructs_in(scene, session)   -> kirby_combat.constructs
  movement_legality.movement_reach(session=) -> kirby_combat.reach

`effects` and `placement` were always combat (a hazard's effect on the
person in it; committing a move to the ledger) and moved up a level, to
`kirby_combat.construct_effects` and `kirby_combat.placement`.
"""
import sys as _sys

import kirby_world.cover
import kirby_world.falling
import kirby_world.generate
import kirby_world.geometry
import kirby_world.hazards
import kirby_world.scene
import kirby_world.visibility

# The pure modules are the SAME module objects, not copies: a class imported
# by either name is one class, and a patch applied by either name is seen by
# both.
for _name in ("cover", "falling", "generate", "geometry", "hazards", "scene", "visibility"):
    _sys.modules[f"{__name__}.{_name}"] = getattr(kirby_world, _name)
    globals()[_name] = getattr(kirby_world, _name)
del _name

from kirby_world.scene import (  # noqa: E402
    Scene, SceneBounds, Surface, Wall, Hazard, HazardEffect,
    Position, AmbientConditions, wall_top_surface, is_climbable,
)
from kirby_world.construct import (  # noqa: E402
    Construct, ConstructEffect, construct_from_wall, construct_from_hazard,
    construct_from_spawn_spec, constructs_containing,
)
from kirby_world.movement_legality import mode_requires_support  # noqa: E402

from kirby_combat.constructs import constructs_in  # noqa: E402
from kirby_combat.construct_effects import (  # noqa: E402
    ConstructEffectResult, resolve_construct_effect,
)

__all__ = [
    "Scene", "SceneBounds", "Surface", "Wall", "Hazard", "HazardEffect",
    "Position", "AmbientConditions", "wall_top_surface", "is_climbable",
    "Construct", "ConstructEffect", "construct_from_wall", "construct_from_hazard",
    "constructs_in",
    "construct_from_spawn_spec", "constructs_containing",
    "ConstructEffectResult", "resolve_construct_effect",
    "mode_requires_support",
]
